from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from jobspy.glassdoor.constant import (
    details_alias,
    details_per_request,
    headers,
    job_type_codes,
    jobs_per_page,
    location_types,
    pay_intervals,
    search_query,
)
from jobspy.model import (
    Compensation,
    JobPost,
    JobResponse,
    Location,
    Scraper,
    ScraperInput,
)
from jobspy.util import (
    create_logger,
    create_session,
    format_description,
    get_enum_from_job_type,
)

log = create_logger("Glassdoor")


class Glassdoor(Scraper):
    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        try:
            self.base_url = scraper_input.country.get_glassdoor_url()
            self.session = create_session(
                proxies=self.proxies, ca_cert=self.ca_cert, user_agent=self.user_agent
            )
            self.session.headers.update(headers)
            variables = self._search_variables()
        except Exception as e:
            log.error(f"Glassdoor: {e}")
            return JobResponse(jobs=[])
        if variables is None:
            return JobResponse(jobs=[])

        job_list: list[JobPost] = []
        seen = set()
        page, cursor, skip = 1, None, scraper_input.offset

        while len(job_list) < scraper_input.results_wanted:
            log.info(f"search page: {page}")
            try:
                response = self._graph(
                    "JobSearchResultsQuery",
                    search_query,
                    {**variables, "pageNumber": page, "pageCursor": cursor},
                )
                if response.status_code != 200:
                    log.error(f"Glassdoor response status code {response.status_code}")
                    break
                answer = response.json()[0]
                result = (answer.get("data") or {}).get("jobListings")
                if not result:
                    raise ValueError(f"API error: {answer.get('errors')}")
                listings = result.get("jobListings") or []
                cursors = result.get("paginationCursors") or []
                cursor = {c["pageNumber"]: c["cursor"] for c in cursors}.get(page + 1)
            except Exception as e:
                log.error(f"Glassdoor: {e}")
                break

            seen_before = len(seen)
            page_jobs: list[JobPost] = []
            for listing in listings:
                try:
                    job = listing["jobview"]
                    job_id = job["job"]["listingId"]
                    if job_id in seen:
                        continue
                    seen.add(job_id)
                    if skip:
                        skip -= 1
                        continue
                    job_post = self._process_job(job)
                except Exception as e:
                    log.warning(f"skipping job: {e}")
                    continue
                if job_post:
                    page_jobs.append(job_post)
                    if len(job_list) + len(page_jobs) >= scraper_input.results_wanted:
                        break

            if scraper_input.fetch_description and page_jobs:
                details = self._fetch_details([job.id for job in page_jobs])
                page_jobs = [
                    job.model_copy(update=details.get(job.id, {})) for job in page_jobs
                ]
            job_list += page_jobs

            if not cursor or len(seen) == seen_before:
                break
            page += 1

        return JobResponse(jobs=job_list)

    def _graph(self, operation: str, query: str, variables: dict):
        return self.session.post(
            f"{self.base_url}/graph",
            json=[{"operationName": operation, "variables": variables, "query": query}],
        )

    def _search_variables(self) -> dict | None:
        """The search's variables, or None when the location isn't found."""
        response = self.session.get(
            f"{self.base_url}/autocomplete/location"
            "?locationTypeFilters=CITY,STATE,COUNTRY&caller=jobs"
            f"&term={quote(self.scraper_input.location or '')}"
        )
        if response.status_code != 200:
            log.error(f"Glassdoor response status code {response.status_code}")
            return None
        variables = {
            "keyword": self.scraper_input.search_term,
            "numJobsToShow": jobs_per_page,
            "filterParams": self._filters(),
        }
        if not self.scraper_input.location:
            return variables
        places = response.json()
        if not places:
            log.error(f"Glassdoor: location '{self.scraper_input.location}' not found")
            return None
        location_id = int(places[0]["locationId"])
        location_type = location_types[places[0]["locationType"]]
        return {
            **variables,
            "locationId": location_id,
            "locationType": location_type,
            "parameterUrlInput": f"IL.0,12_I{location_type}{location_id}",
        }

    def _filters(self) -> list[dict]:
        filters = {}
        if self.scraper_input.location and self.scraper_input.distance is not None:
            filters["radius"] = self.scraper_input.distance
        if hours_old := self.scraper_input.hours_old:
            filters["fromAge"] = math.ceil(hours_old / 24)
        job_type = self.scraper_input.job_type
        if code := job_type_codes.get(job_type):
            filters["jobType"] = code
        elif job_type:
            log.warning(
                f"Glassdoor: job_type {job_type.value[0]} isn't supported, ignoring it"
            )
        if self.scraper_input.is_remote:
            filters["remoteWorkType"] = 1
        if self.scraper_input.easy_apply:
            filters["applicationType"] = 1
        return [
            {"filterKey": key, "values": str(value)} for key, value in filters.items()
        ]

    def _process_job(self, job: dict) -> JobPost | None:
        header = job["header"]
        age = header["ageInDays"]
        hours_old = self.scraper_input.hours_old
        if hours_old and age >= math.ceil(hours_old / 24):
            return None

        job_id = int(job["job"]["listingId"])
        company_id = header["employer"]["id"]
        company = job["overview"]
        website = company.get("website")
        if website and not website.startswith("http"):
            website = f"https://{website}"
        job_types = [
            job_type
            for key in header.get("jobTypeKeys") or []
            if (job_type := get_enum_from_job_type(key.rpartition(".")[2]))
        ]
        return JobPost(
            id=f"gd-{job_id}",
            title=job["job"]["jobTitleText"],
            company_name=header["employerNameFromSearch"],
            company_url=(
                f"{self.base_url}/Overview/W-EI_IE{company_id}.htm"
                if company_id
                else None
            ),
            company_logo=company.get("squareLogoUrl"),
            location=self._parse_location(header, job["map"]["country"]),
            job_url=f"{self.base_url}/job-listing/j?jl={job_id}",
            date_posted=datetime.now(timezone.utc).date() - timedelta(days=age),
            job_type=job_types or None,
            is_remote="WORK_FROM_HOME" in (header.get("remoteWorkTypes") or [])
            or header.get("locationName") == "Remote",
            compensation=self._parse_salary(header),
            listing_type=header["adOrderSponsorshipLevel"].lower(),
            company_rating=header.get("rating") or None,
            company_industry=(company.get("primaryIndustry") or {}).get("industryName"),
            company_url_direct=website or None,
            company_addresses=company.get("headquarters"),
            company_num_employees=company.get("size"),
            company_revenue=company.get("revenue"),
            company_description=(company.get("overview") or {}).get("description"),
        )

    @staticmethod
    def _parse_salary(header: dict) -> Compensation | None:
        pay = header["payPeriodAdjustedPay"]
        if not pay:
            return None
        return Compensation(
            interval=pay_intervals.get(header["payPeriod"]),
            min_amount=round(pay["p10"], 2),
            max_amount=round(pay["p90"], 2),
            currency=header["payCurrency"],
        )

    @staticmethod
    def _parse_location(header: dict, country: str | None) -> Location | None:
        """locationName is a city ("Chicago, IL", "Paris"), a state ("Oregon"), a country or "Remote"."""
        name, kind = header["locationName"], header["locationType"]
        if not name or name == "Remote":
            return None
        if kind == "N":
            return Location(country=country or name)
        if kind == "S":
            return Location(state=name, country=country)
        city, *rest = name.split(", ")
        return Location(city=city, state=rest[-1] if rest else None, country=country)

    def _fetch_details(self, job_ids: list[str]) -> dict:
        """The description and emails by job id, one request for every 25 jobs."""
        details = {}
        try:
            for start in range(0, len(job_ids), details_per_request):
                aliases = "".join(
                    details_alias % (job_id[3:], job_id[3:])
                    for job_id in job_ids[start : start + details_per_request]
                )
                response = self._graph("JobDetails", f"query JobDetails {{{aliases}}}", {})
                if response.status_code != 200:
                    log.warning(
                        f"Glassdoor response status code {response.status_code} "
                        "for job details"
                    )
                    break
                for alias, view in response.json()[0]["data"].items():
                    if view:
                        description, emails = format_description(
                            view["job"]["description"],
                            self.scraper_input.description_format,
                        )
                        details[f"gd-{alias[1:]}"] = {
                            "description": description,
                            "emails": emails,
                        }
        except Exception as e:
            log.warning(f"Glassdoor: job details: {e}")
        return details
