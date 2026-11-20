from __future__ import annotations

import math

from jobspy.model import (
    Compensation,
    Country,
    JobPost,
    Location,
    Scraper,
    ScraperInput,
)
from jobspy.seek.constant import (
    details_alias,
    job_type_codes,
    job_type_labels,
    jobs_per_page,
    km_per_mile,
    markets,
    max_distance_km,
    pay_intervals,
    private_advertiser,
    rate_limited,
    remote_arrangement,
    salary_pattern,
    thousands_separator,
)
from jobspy.seek.model import Job, JobDetails, JobSearch, Market
from jobspy.util import (
    TLSRotating,
    check_status,
    create_session,
    description_fields,
    too_old,
)


class Seek(Scraper):
    base_url = "https://au.seek.com"
    search_url = f"{base_url}/api/jobsearch/v5/search"
    graphql_url = f"{base_url}/graphql"

    def scrape(self, scraper_input: ScraperInput) -> list[JobPost]:
        self.scraper_input = scraper_input
        self.country = scraper_input.country_indeed
        if self.country not in markets:
            self.warn(
                f"country_indeed {self.country.value} isn't supported, skipping it"
            )
            return []
        self.market = markets[self.country]
        self.session = create_session(TLSRotating(scraper_input.proxies), scraper_input)
        params = self._search_params()
        job_list: list[JobPost] = []
        seen: set[object] = set()
        first_page = page = scraper_input.offset // jobs_per_page + 1
        skip = scraper_input.offset % jobs_per_page

        while len(job_list) < scraper_input.results_wanted:
            self.log.info(f"search page: {page}")
            try:
                response = self.session.get(
                    self.search_url, params=params | {"page": page}
                )
                check_status(response)
                search = JobSearch.model_validate(response.json())
                last_page = math.ceil(search.totalCount / jobs_per_page)
                jobs: dict[object, dict[str, object]] = {}
                for row in search.data:
                    jobs.setdefault(row.get("id"), row)
                new_jobs = [job for key, job in jobs.items() if key not in seen]
                seen.update(jobs)
            except Exception as e:
                self.fail(str(e))
                break
            place = scraper_input.location
            if page == 1 and place and not search.location:
                if place.strip().lower() != self.country.value:
                    self.warn(f"location '{place}' not found")

            page_jobs: list[JobPost] = []
            stale = False
            for job in new_jobs[skip if page == first_page else 0 :]:
                try:
                    job_post = self._process_job(job)
                except Exception as e:
                    self.log.warning(f"skipping job: {e}")
                    continue
                if not job_post:
                    stale = True
                    continue
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

            if not new_jobs or (stale and not page_jobs) or page >= last_page:
                break
            page += 1

        return job_list

    def _search_params(self) -> dict[str, str | int]:
        params: dict[str, str | int | None] = {
            "siteKey": self.market.site_key,
            "pageSize": jobs_per_page,
            "keywords": self.scraper_input.search_term,
            "where": self.scraper_input.location,
        }
        distance = self.scraper_input.distance
        if self.scraper_input.location and distance is not None:
            params["distance"] = min(round(distance * km_per_mile), max_distance_km)
        if hours_old := self.scraper_input.hours_old:
            params["daterange"] = max(2, math.ceil(hours_old / 24))
            params["sortmode"] = "ListedDate"
        job_type = self.scraper_input.job_type
        if job_type in job_type_codes:
            params["worktype"] = job_type_codes[job_type]
        elif job_type:
            self.warn(f"job_type {job_type.value} isn't supported, ignoring it")
        if self.scraper_input.is_remote:
            params["workarrangement"] = remote_arrangement
        if self.scraper_input.easy_apply:
            self.warn("easy_apply isn't supported, ignoring it")
        return {name: value for name, value in params.items() if value is not None}

    def _process_job(self, raw: dict[str, object]) -> JobPost | None:
        job = Job.model_validate(raw)
        if too_old(job.listingDate.timestamp(), self.scraper_input.hours_old):
            return None
        job_types = [
            job_type
            for label in job.workTypes
            for job_type in job_type_labels.get(label, [])
        ]
        company = job.companyName or job.advertiser
        return JobPost(
            id=f"seek-{job.id}",
            title=job.title,
            company=None if company == private_advertiser else company,
            company_url=job.companyUrl,
            company_logo=job.serpLogoUrl,
            location=self._parse_location(job.location, self.country),
            job_url=f"https://{self.market.domain}/job/{job.id}",
            date_posted=job.listingDate.date(),
            job_type=job_types or None,
            is_remote=any(a.id == remote_arrangement for a in job.arrangements),
            **self._parse_salary(job, self.market).model_dump(),
            listing_type=job.jobAdType.lower() if job.jobAdType else None,
            job_function=job.classification,
        )

    @staticmethod
    def _parse_location(label: str | None, country: Country) -> Location:
        """label is "Suburb, Area", an area alone ("Sydney NSW") or the country."""
        if not label or label.lower() == country.value:
            return Location(country=country)
        city, comma, state = label.partition(", ")
        if not comma:
            return Location(state=label, country=country)
        return Location(city=city, state=state, country=country)

    @staticmethod
    def _parse_salary(job: Job, market: Market) -> Compensation:
        match = salary_pattern.fullmatch(job.salaryLabel or "")
        if not match:
            return Compensation()
        if not job.currencyLabel and match["symbol"] != market.currency_symbol:
            return Compensation()
        low, high = (
            float(thousands_separator.sub("", amount).replace(",", "."))
            for amount in (match["low"], match["high"] or match["low"])
        )
        return Compensation(
            interval=pay_intervals[match["unit"]],
            min_amount=low,
            max_amount=high,
            currency=job.currencyLabel or market.currency,
        )

    def _fetch_details(self, job_ids: list[str]) -> dict[str, dict[str, object]]:
        """The description and company details by job id, in one request."""
        details: dict[str, dict[str, object]] = {}
        try:
            aliases = "".join(
                details_alias % (job_id[5:], job_id[5:]) for job_id in job_ids
            )
            response = self.session.post(
                self.graphql_url,
                json={
                    "query": f"query($zone: Zone!) {{{aliases}}}",
                    "variables": {"zone": self.market.zone},
                },
            )
            check_status(response)
            answer = response.json()
            errors = answer.get("errors") or []
            codes = [(error.get("extensions") or {}).get("code") for error in errors]
            warning = "job details rate limited: use proxies"
            if rate_limited in codes:
                if warning not in self.warnings:
                    self.warn(warning)
            elif errors:
                self.warn(f"job details: {errors[0].get('message')}")
            for alias, raw in (answer.get("data") or {}).items():
                job = JobDetails.model_validate(raw or {})
                details[f"seek-{alias[1:]}"] = {
                    **description_fields(
                        job.content, self.scraper_input.description_format
                    ),
                    "company_industry": job.industry,
                    "company_url_direct": job.website,
                    "company_addresses": job.primaryLocation,
                    "company_num_employees": job.size,
                    "company_description": job.description,
                    "company_rating": job.rating,
                    "company_reviews_count": job.reviews,
                }
        except Exception as e:
            self.warn(f"job details: {e}")
        return details
