from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from curl_cffi.requests import Response

from jobspy.glassdoor.constant import (
    details_alias,
    details_per_request,
    domains,
    headers,
    job_type_codes,
    jobs_per_page,
    location_types,
    pay_intervals,
    search_query,
)
from jobspy.glassdoor.model import (
    Header,
    JobListings,
    JobView,
    Listing,
    Place,
)
from jobspy.indeed.constant import country_codes
from jobspy.model import (
    Compensation,
    JobPost,
    Location,
    Scraper,
    ScraperInput,
)
from jobspy.util import (
    TLSRotating,
    check_status,
    create_session,
    description_fields,
    get_enum_from_job_type,
)


class Glassdoor(Scraper):
    def scrape(self, scraper_input: ScraperInput) -> list[JobPost]:
        self.scraper_input = scraper_input
        country = scraper_input.country_indeed
        if country not in domains:
            self.warn(f"country_indeed {country.value} isn't supported, skipping it")
            return []
        try:
            self.base_url = f"https://{domains[country]}"
            self.session = create_session(
                TLSRotating(scraper_input.proxies), scraper_input, headers
            )
            variables = self._search_variables()
        except Exception as e:
            self.fail(str(e))
            return []
        if variables is None:
            return []

        job_list: list[JobPost] = []
        seen: set[int | None] = set()
        page, skip = 1, scraper_input.offset
        cursor: str | None = None

        while len(job_list) < scraper_input.results_wanted:
            self.log.info(f"search page: {page}")
            try:
                response = self._graph(
                    "JobSearchResultsQuery",
                    search_query,
                    {**variables, "pageNumber": page, "pageCursor": cursor},
                )
                check_status(response)
                answer = response.json()[0]
                result = (answer.get("data") or {}).get("jobListings")
                if not result:
                    raise ValueError(f"API error: {answer.get('errors')}")
                job_listings = JobListings.model_validate(result)
                listings = job_listings.jobListings or []
                cursors = job_listings.paginationCursors or []
                cursor = {c.pageNumber: c.cursor for c in cursors}.get(page + 1)
            except Exception as e:
                self.fail(str(e))
                break

            seen_before = len(seen)
            page_jobs: list[JobPost] = []
            for listing in listings:
                try:
                    entry = Listing.model_validate(listing)
                    job, job_id = entry.jobview, entry.listingId
                    if job_id in seen:
                        continue
                    seen.add(job_id)
                    if skip:
                        skip -= 1
                        continue
                    job_post = self._process_job(job)
                except Exception as e:
                    self.log.warning(f"skipping job: {e}")
                    continue
                if job_post:
                    page_jobs.append(job_post)
                    if len(job_list) + len(page_jobs) >= scraper_input.results_wanted:
                        break

            if scraper_input.fetch_description and page_jobs:
                details = self._fetch_details([job.id for job in page_jobs if job.id])
                page_jobs = [
                    job.model_copy(update=details[job.id] if job.id in details else {})
                    for job in page_jobs
                ]
            job_list += page_jobs

            if not cursor or len(seen) == seen_before:
                break
            page += 1

        return job_list

    def _graph(
        self, operation: str, query: str, variables: dict[str, object]
    ) -> Response:
        return self.session.post(
            f"{self.base_url}/graph",
            json=[{"operationName": operation, "variables": variables, "query": query}],
        )

    def _search_variables(self) -> dict[str, object] | None:
        """The search's variables, or None when the location isn't found."""
        location = self.scraper_input.location or ""
        places = self._places(location)
        variables: dict[str, object] = {
            "keyword": self.scraper_input.search_term,
            "numJobsToShow": jobs_per_page,
            "filterParams": self._filters(),
        }
        if not location:
            return variables
        city = location.split(",")[0].strip()
        if not places and city and city != location:
            # glassdoor.de finds "Berlin", not "Berlin, Germany"
            code = country_codes[self.scraper_input.country_indeed]
            places = [
                p for p in self._places(city) if p.get("country2LetterIso") == code
            ]
        if not places:
            self.fail(f"location '{location}' not found")
            return None
        place = Place.model_validate(places[0])
        location_id = place.locationId
        location_type = location_types[place.locationType]
        return {
            **variables,
            "locationId": location_id,
            "locationType": location_type,
            "parameterUrlInput": f"IL.0,12_I{location_type}{location_id}",
        }

    def _places(self, term: str) -> list[dict[str, object]]:
        """Places matching the term. The request also sets the search cookies."""
        response = self.session.get(
            f"{self.base_url}/autocomplete/location"
            "?locationTypeFilters=CITY,STATE,COUNTRY&caller=jobs"
            f"&term={quote(term)}"
        )
        check_status(response)
        if not term:
            return []
        places: list[dict[str, object]] = response.json()
        return places

    def _filters(self) -> list[dict[str, str]]:
        filters: dict[str, str | int] = {}
        if self.scraper_input.location and self.scraper_input.distance is not None:
            filters["radius"] = self.scraper_input.distance
        if hours_old := self.scraper_input.hours_old:
            filters["fromAge"] = math.ceil(hours_old / 24)
        job_type = self.scraper_input.job_type
        if job_type in job_type_codes:
            filters["jobType"] = job_type_codes[job_type]
        elif job_type:
            self.warn(f"job_type {job_type.value} isn't supported, ignoring it")
        if self.scraper_input.is_remote:
            filters["remoteWorkType"] = 1
        if self.scraper_input.easy_apply:
            filters["applicationType"] = 1
        return [
            {"filterKey": key, "values": str(value)} for key, value in filters.items()
        ]

    def _process_job(self, raw: dict[str, object]) -> JobPost | None:
        job = JobView.model_validate(raw)
        header = job.header
        age = header.ageInDays
        hours_old = self.scraper_input.hours_old
        if hours_old and age >= math.ceil(hours_old / 24):
            return None

        job_id = job.listingId
        company_id = header.id
        company = job.overview
        website = company.website
        if website and not website.startswith("http"):
            website = f"https://{website}"
        job_types = [
            job_type
            for key in header.jobTypeKeys or []
            if (job_type := get_enum_from_job_type(key.rpartition(".")[2]))
        ]
        return JobPost(
            id=f"gd-{job_id}",
            title=job.jobTitleText,
            company=header.employerNameFromSearch,
            company_url=(
                f"{self.base_url}/Overview/W-EI_IE{company_id}.htm"
                if company_id
                else None
            ),
            company_logo=company.squareLogoUrl,
            location=self._parse_location(header, job.country),
            job_url=f"{self.base_url}/job-listing/j?jl={job_id}",
            date_posted=datetime.now(timezone.utc).date() - timedelta(days=age),
            job_type=job_types or None,
            is_remote="WORK_FROM_HOME" in (header.remoteWorkTypes or [])
            or header.locationName == "Remote",
            **self._parse_salary(header).model_dump(),
            listing_type=header.adOrderSponsorshipLevel.lower(),
            company_rating=header.rating or None,
            company_industry=company.industryName,
            company_url_direct=website or None,
            company_addresses=company.headquarters,
            company_num_employees=company.size,
            company_revenue=company.revenue,
            company_description=company.description,
        )

    @staticmethod
    def _parse_salary(header: Header) -> Compensation:
        pay = header.payPeriodAdjustedPay
        if not pay:
            return Compensation()
        return Compensation(
            interval=pay_intervals.get(header.payPeriod or ""),
            min_amount=round(pay.p10, 2),
            max_amount=round(pay.p90, 2),
            currency=header.payCurrency,
        )

    @staticmethod
    def _parse_location(header: Header, country: str | None) -> Location | None:
        """locationName is a city ("Chicago, IL", "Paris"), a state ("Oregon"), a country or "Remote"."""
        name, kind = header.locationName, header.locationType
        if not name or name == "Remote":
            return None
        if kind == "N":
            return Location(country=country or name)
        if kind == "S":
            return Location(state=name, country=country)
        city, *rest = name.split(", ")
        return Location(city=city, state=rest[-1] if rest else None, country=country)

    def _fetch_details(self, job_ids: list[str]) -> dict[str, dict[str, object]]:
        """The description and emails by job id, one request for every 25 jobs."""
        details: dict[str, dict[str, object]] = {}
        try:
            for start in range(0, len(job_ids), details_per_request):
                aliases = "".join(
                    details_alias % (job_id[3:], job_id[3:])
                    for job_id in job_ids[start : start + details_per_request]
                )
                response = self._graph(
                    "JobDetails", f"query JobDetails {{{aliases}}}", {}
                )
                check_status(response)
                for alias, view in response.json()[0]["data"].items():
                    if view:
                        details[f"gd-{alias[1:]}"] = description_fields(
                            view["job"]["description"],
                            self.scraper_input.description_format,
                        )
        except Exception as e:
            self.log.warning(f"job details: {e}")
        return details
