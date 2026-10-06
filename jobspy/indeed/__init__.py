from __future__ import annotations

import json
from urllib.parse import urlsplit

from jobspy.indeed.constant import (
    countries,
    default_distance,
    headers,
    hybrid_key,
    job_search_query,
    job_type_codes,
    jobs_per_page,
    full_time_is_permanent_in,
    languages,
    permanent_key,
    remote_key,
)
from jobspy.indeed.util import get_compensation, get_job_type, is_job_remote
from jobspy.model import (
    JobPost,
    JobResponse,
    JobType,
    Location,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.util import create_logger, create_session, format_description, utc_date

log = create_logger("Indeed")


class Indeed(Scraper):
    api_url = "https://apis.indeed.com/graphql"

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.INDEED, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent
        )
        self.session = create_session(
            proxies=self.proxies, ca_cert=ca_cert, is_tls=False
        )
        self.scraper_input = None
        self.base_url = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        domain, country_code = scraper_input.country.indeed_domain_value
        self.base_url = f"https://{domain}.indeed.com"
        language = languages.get(country_code, "en")
        request_headers = headers | {
            "indeed-co": country_code,
            "indeed-locale": f"{language}-{country_code}",
        }
        if self.user_agent:
            if "Indeed App" in self.user_agent:
                request_headers["user-agent"] = self.user_agent
            else:
                log.warning(
                    f"Indeed: user_agent '{self.user_agent}' isn't accepted by the site, using the default"
                )
        filters = self._build_filters()
        job_list: list[JobPost] = []
        seen = set()
        skip = scraper_input.offset
        cursor = None
        page = 1

        while len(job_list) < scraper_input.results_wanted:
            log.info(f"search page: {page}")
            try:
                response = self.session.post(
                    self.api_url,
                    headers=request_headers,
                    json={"query": self._build_query(filters, cursor)},
                )
                if response.status_code != 200:
                    log.error(f"Indeed response status code {response.status_code}")
                    break
                data = response.json()
                search = (data.get("data") or {}).get("jobSearch")
                if not search:
                    log.error(f"Indeed: {data.get('errors')}")
                    break
                jobs = {
                    result["job"]["key"]: result["job"]
                    for result in search["results"]
                    if result["job"]
                }
                new_jobs = [job for key, job in jobs.items() if key not in seen]
                seen.update(jobs)
                cursor = search["pageInfo"]["nextCursor"]
            except Exception as e:
                log.error(f"Indeed: {e}")
                break

            for job in new_jobs[skip:]:
                try:
                    job_list.append(self._process_job(job))
                except Exception as e:
                    log.warning(f"skipping job: {e}")
                    continue
                if len(job_list) >= scraper_input.results_wanted:
                    break
            skip = max(skip - len(new_jobs), 0)

            if not new_jobs or not cursor:
                break
            page += 1

        return JobResponse(jobs=job_list)

    def _build_query(self, filters: str, cursor: str | None) -> str:
        search_term = self.scraper_input.search_term
        location = self.scraper_input.location
        distance = self.scraper_input.distance
        if distance is None:
            distance = default_distance
        return job_search_query.format(
            what=(
                f"what: {json.dumps(search_term, ensure_ascii=False)}"
                if search_term
                else ""
            ),
            location=(
                f"location: {{where: {json.dumps(location, ensure_ascii=False)}, radius: {distance}, radiusUnit: MILES}}"
                if location
                else ""
            ),
            limit=jobs_per_page,
            cursor=f'cursor: "{cursor}"' if cursor else "",
            filters=filters,
        )

    def _build_filters(self) -> str:
        def attribute(key, match=""):
            return f'{{ keyword: {{ field: "attributes", keys: ["{key}"]{match} }} }}'

        filters = []
        if self.scraper_input.hours_old:
            filters.append(
                f'{{ date: {{ field: "dateOnIndeed", start: "{self.scraper_input.hours_old}h" }} }}'
            )

        job_type = self.scraper_input.job_type
        keys = list(job_type_codes.get(job_type, ()))
        if job_type and not keys:
            log.warning(
                f"Indeed: job_type {job_type.value[0]} isn't supported, ignoring it"
            )
        if (
            job_type == JobType.FULL_TIME
            and self.scraper_input.country == full_time_is_permanent_in
        ):
            keys.append(permanent_key)
        if len(keys) > 1:
            any_key = ", ".join(attribute(key) for key in keys)
            filters.append(
                f"{{ composite: {{ filters: [{any_key}], operation: OR }} }}"
            )
        elif keys:
            filters.append(attribute(keys[0]))
        if self.scraper_input.is_remote:
            filters.append(attribute(remote_key))
            filters.append(attribute(hybrid_key, ", match: MUST_NOT"))

        if self.scraper_input.easy_apply:
            filters.append(
                '{ keyword: { field: "indeedApplyScope", keys: ["DESKTOP"] } }'
            )
        return f"filters: [{', '.join(filters)}]" if filters else ""

    def _process_job(self, job: dict) -> JobPost:
        description, emails = format_description(
            job["description"]["html"], self.scraper_input.description_format
        )

        employer = job["employer"] or {}
        dossier = employer.get("dossier") or {}
        details = dossier.get("employerDetails") or {}
        company_page = employer.get("relativeCompanyPageUrl")
        rating = ((employer.get("ugcStats") or {}).get("ratings") or {}).get(
            "overallRating"
        ) or {}
        location = job["location"]
        country_code = location.get("countryCode")
        apply_url = job["recruit"]["viewJobUrl"]
        if f".{urlsplit(apply_url).hostname}".endswith(".indeed.com"):
            apply_url = None
        return JobPost(
            id=f'in-{job["key"]}',
            title=job["title"],
            description=description,
            company_name=employer.get("name") or job["sourceEmployerName"],
            company_url=f"{self.base_url}{company_page}" if company_page else None,
            company_url_direct=(dossier.get("links") or {}).get("corporateWebsite"),
            location=Location(
                city=location.get("city"),
                state=location.get("admin1Code"),
                country=countries.get(country_code, country_code),
            ),
            job_type=get_job_type(job["attributes"], self.scraper_input.country),
            compensation=get_compensation(job["compensation"]),
            date_posted=utc_date(job["dateOnIndeed"] / 1000),
            job_url=f'{self.base_url}/viewjob?jk={job["key"]}',
            job_url_direct=apply_url,
            emails=emails,
            is_remote=is_job_remote(job["attributes"]),
            company_addresses=(details.get("addresses") or [None])[0],
            company_industry=(
                details["industry"].replace("Iv1", "").replace("_", " ").title().strip()
                if details.get("industry")
                else None
            ),
            company_num_employees=details.get("employeesLocalizedLabel"),
            company_revenue=details.get("revenueLocalizedLabel"),
            company_description=details.get("briefDescription"),
            company_logo=(dossier.get("images") or {}).get("squareLogoUrl"),
            company_rating=rating.get("value") if rating.get("count") else None,
            company_reviews_count=rating.get("count") or None,
        )
