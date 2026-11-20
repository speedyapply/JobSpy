from __future__ import annotations

import math
import random
import time

from jobspy.model import (
    Compensation,
    Country,
    JobPost,
    JobType,
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
    too_old,
)
from jobspy.ziprecruiter.constant import (
    job_type_codes,
    jobs_per_page,
    pay_intervals,
)
from jobspy.ziprecruiter.model import EmploymentType, Job, JobDetails, JobSearch, Pay
from jobspy.ziprecruiter.util import direct_url, page_values


class ZipRecruiter(Scraper):
    base_url = "https://www.ziprecruiter.com"
    delay = (3, 7)

    def scrape(self, scraper_input: ScraperInput) -> list[JobPost]:
        self.scraper_input = scraper_input
        self.session = create_session(TLSRotating(scraper_input.proxies), scraper_input)
        if not scraper_input.proxies:
            self.session.impersonate = "safari"
        params = self._search_params()
        job_list: list[JobPost] = []
        seen: set[object] = set()
        first_page = page = scraper_input.offset // jobs_per_page + 1
        skip = scraper_input.offset % jobs_per_page

        while len(job_list) < scraper_input.results_wanted:
            if page > first_page:
                time.sleep(random.uniform(*self.delay))
            self.log.info(f"search page: {page}")
            try:
                # /jobs-search/1 redirects to /jobs-search
                path = "/jobs-search" if page == 1 else f"/jobs-search/{page}"
                response = self.session.get(self.base_url + path, params=params)
                check_status(response)
                search = JobSearch.model_validate(
                    page_values(response.text, "jobKeysMap", "jobCards", "jobCount")
                )
                last_page = math.ceil(search.jobCount / jobs_per_page)
                jobs = {job.get("listingKey"): job for job in search.jobs}
                new_jobs = [job for key, job in jobs.items() if key not in seen]
                seen.update(jobs)
            except Exception as e:
                self.fail(str(e))
                break

            for job in new_jobs[skip if page == first_page else 0 :]:
                try:
                    job_post = self._process_job(job)
                except Exception as e:
                    self.log.warning(f"skipping job: {e}")
                    continue
                if job_post:
                    job_list.append(job_post)
                    if len(job_list) >= scraper_input.results_wanted:
                        break

            if not new_jobs or page >= last_page:
                break
            page += 1

        return job_list

    def _search_params(self) -> dict[str, str | int]:
        search_term = self.scraper_input.search_term
        job_type = self.scraper_input.job_type
        if job_type == JobType.INTERNSHIP:
            if "internship" not in (search_term or "").lower():
                search_term = f"{search_term or ''} internship".strip()
        elif job_type and job_type not in job_type_codes:
            self.warn(f"job_type {job_type.value} isn't supported, ignoring it")
        params: dict[str, str | int | None] = {
            "search": search_term,
            "location": self.scraper_input.location,
            "radius": self.scraper_input.distance,
        }
        if hours_old := self.scraper_input.hours_old:
            params["days"] = math.ceil(hours_old / 24)
        if job_type in job_type_codes:
            params["refine_by_employment"] = job_type_codes[job_type]
        if self.scraper_input.is_remote:
            params["refine_by_location_type"] = "only_remote"
        if self.scraper_input.easy_apply:
            params["refine_by_apply_type"] = "has_zipapply"
        return {name: value for name, value in params.items() if value}

    def _process_job(self, raw: object) -> JobPost | None:
        job = Job.model_validate(raw)
        posted = job.postedAtUtc
        if too_old(posted.timestamp(), self.scraper_input.hours_old):
            return None
        job_type = self._parse_job_type(job.employmentTypes)
        if self.scraper_input.job_type == JobType.INTERNSHIP and (
            JobType.INTERNSHIP not in (job_type or [])
        ):
            return None

        country = Country.CANADA if job.countryCode == "CA" else Country.USA
        apply_url = job.applyButtonConfig.externalApplyUrl
        job_post = JobPost(
            id=f"zr-{job.listingKey}",
            title=job.title,
            company=job.name,
            company_url=self.base_url + job.companyUrl if job.companyUrl else None,
            company_logo=job.logoUrl,
            location=Location(city=job.city, state=job.stateCode, country=country),
            job_url=self.base_url + job.rawCanonicalZipJobPageUrl,
            job_url_direct=direct_url(apply_url) if apply_url else None,
            date_posted=posted.date(),
            job_type=job_type,
            # REMOTE or REMOTE_OPTIONAL
            is_remote=any("REMOTE" in t.name for t in job.locationTypes),
            **self._parse_salary(job.pay).model_dump(),
        )
        if self.scraper_input.fetch_description:
            details = self._fetch_details(job.listingKey, job_post.job_url)
            job_post = job_post.model_copy(update=details)
        return job_post

    @staticmethod
    def _parse_job_type(types: list[EmploymentType]) -> list[JobType] | None:
        names = (t.name.split("NAME_")[1].replace("_", "").lower() for t in types)
        return [
            t
            for name in names
            if (t := get_enum_from_job_type(name.replace("contractor", "contract")))
        ] or None

    @staticmethod
    def _parse_salary(pay: Pay) -> Compensation:
        if not pay.visible:
            return Compensation()
        if pay.currency is None:
            raise ValueError("no pay currency")
        return Compensation(
            interval=pay_intervals.get(pay.interval or ""),
            min_amount=pay.min,
            max_amount=pay.max,
            currency=pay.currency.removeprefix("PAY_CURRENCY_"),
        )

    def _fetch_details(self, job_id: str | None, job_url: str) -> dict[str, object]:
        try:
            response = self.session.get(job_url, allow_redirects=True)
            check_status(response)
            job = JobDetails.model_validate(
                page_values(response.text, "jobDetails")["jobDetails"]
            )
            fields = description_fields(
                job.htmlFullDescription, self.scraper_input.description_format
            )
        except Exception as e:
            self.warn(f"job {job_id}: {e}")
            return {}

        industries = job.canonicalIndustries
        website = job.canonicalWebsite
        rating = job.rating
        return {
            **fields,
            "company_industry": industries[0] if industries else None,
            "company_url_direct": f"https://{website}" if website else None,
            "company_num_employees": job.companySizeDisplay,
            "company_addresses": job.hqLocation,
            "company_description": job.about or job.description,
            "company_rating": round(rating / 2, 2) if rating else None,
        }
