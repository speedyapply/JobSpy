from __future__ import annotations

import json
from urllib.parse import urlsplit

from jobspy.indeed.constant import (
    countries,
    country_codes,
    default_distance,
    full_time_is_permanent_in,
    headers,
    hybrid_key,
    job_search_query,
    job_type_codes,
    jobs_per_page,
    languages,
    permanent_key,
    remote_key,
    subdomains,
)
from jobspy.indeed.model import Employer, Job, JobSearch
from jobspy.indeed.util import get_compensation, get_job_type, is_job_remote
from jobspy.model import (
    JobPost,
    JobType,
    Location,
    Scraper,
    ScraperInput,
)
from jobspy.util import (
    RequestsRotating,
    check_status,
    create_session,
    description_fields,
    utc_date,
)


class Indeed(Scraper):
    api_url = "https://apis.indeed.com/graphql"

    def scrape(self, scraper_input: ScraperInput) -> list[JobPost]:
        self.scraper_input = scraper_input
        country_code = country_codes[scraper_input.country_indeed]
        domain = subdomains.get(scraper_input.country_indeed, country_code.lower())
        self.base_url = f"https://{domain}.indeed.com"
        language = languages.get(country_code, "en")
        self.session = create_session(
            RequestsRotating(scraper_input.proxies),
            scraper_input,
            headers
            | {
                "indeed-co": country_code,
                "indeed-locale": f"{language}-{country_code}",
            },
        )
        filters = self._build_filters()
        job_list: list[JobPost] = []
        seen: set[object] = set()
        skip = scraper_input.offset
        cursor = None
        page = 1

        while len(job_list) < scraper_input.results_wanted:
            self.log.info(f"search page: {page}")
            try:
                response = self.session.post(
                    self.api_url,
                    json={"query": self._build_query(filters, cursor)},
                )
                check_status(response)
                data = response.json()
                search = (data.get("data") or {}).get("jobSearch")
                if not search:
                    raise ValueError(f"API error: {data.get('errors')}")
                job_search = JobSearch.model_validate(search)
                jobs = {
                    result.job["key"]: result.job
                    for result in job_search.results
                    if result.job
                }
                new_jobs = [job for key, job in jobs.items() if key not in seen]
                seen.update(jobs)
                cursor = job_search.nextCursor
            except Exception as e:
                self.fail(str(e))
                break

            for job in new_jobs[skip:]:
                try:
                    job_list.append(self._process_job(job))
                except Exception as e:
                    self.log.warning(f"skipping job: {e}")
                    continue
                if len(job_list) >= scraper_input.results_wanted:
                    break
            skip = max(skip - len(new_jobs), 0)

            if not new_jobs or not cursor:
                break
            page += 1

        return job_list

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
        def attribute(key: str, match: str = "") -> str:
            return f'{{ keyword: {{ field: "attributes", keys: ["{key}"]{match} }} }}'

        filters = []
        if self.scraper_input.hours_old:
            filters.append(
                f'{{ date: {{ field: "dateOnIndeed", start: "{self.scraper_input.hours_old}h" }} }}'
            )

        job_type = self.scraper_input.job_type
        keys = list(job_type_codes[job_type]) if job_type in job_type_codes else []
        if job_type and not keys:
            self.warn(f"job_type {job_type.value} isn't supported, ignoring it")
        if (
            job_type == JobType.FULL_TIME
            and self.scraper_input.country_indeed == full_time_is_permanent_in
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

    def _process_job(self, raw: dict[str, object]) -> JobPost:
        job = Job.model_validate(raw)
        fields = description_fields(job.html, self.scraper_input.description_format)

        employer = job.employer or Employer()
        company_page = employer.relativeCompanyPageUrl
        location = job.location
        country_code = location.countryCode
        apply_url = job.viewJobUrl
        if apply_url and f".{urlsplit(apply_url).hostname}".endswith(".indeed.com"):
            apply_url = None
        return JobPost(
            id=f"in-{job.key}",
            title=job.title,
            company=employer.name or job.sourceEmployerName,
            company_url=f"{self.base_url}{company_page}" if company_page else None,
            company_url_direct=employer.corporateWebsite,
            location=Location(
                city=location.city,
                state=location.admin1Code,
                country=country_code and countries.get(country_code, country_code),
            ),
            job_type=get_job_type(job.attributes, self.scraper_input.country_indeed),
            **get_compensation(job.compensation).model_dump(),
            date_posted=utc_date(job.dateOnIndeed / 1000),
            job_url=f"{self.base_url}/viewjob?jk={job.key}",
            job_url_direct=apply_url,
            is_remote=is_job_remote(job.attributes),
            company_addresses=employer.addresses[0] if employer.addresses else None,
            company_industry=(
                employer.industry.replace("Iv1", "").replace("_", " ").title().strip()
                if employer.industry
                else None
            ),
            company_num_employees=employer.employeesLocalizedLabel,
            company_revenue=employer.revenueLocalizedLabel,
            company_description=employer.briefDescription,
            company_logo=employer.squareLogoUrl,
            company_rating=employer.value if employer.count else None,
            company_reviews_count=employer.count or None,
        ).model_copy(update=fields)
