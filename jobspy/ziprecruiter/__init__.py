from __future__ import annotations

import math
import random
import time
from datetime import datetime

from jobspy.model import (
    Compensation,
    Country,
    JobPost,
    JobResponse,
    JobType,
    Location,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.util import (
    create_logger,
    create_session,
    format_description,
    get_enum_from_job_type,
)
from jobspy.ziprecruiter.constant import (
    browser_user_agent,
    job_type_codes,
    jobs_per_page,
    pay_intervals,
)
from jobspy.ziprecruiter.util import direct_url, page_values

log = create_logger("ZipRecruiter")


class ZipRecruiter(Scraper):
    base_url = "https://www.ziprecruiter.com"
    delay = 3
    band_delay = 4

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.ZIP_RECRUITER, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent
        )
        self.scraper_input = None
        self.session = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.session = create_session(proxies=self.proxies, ca_cert=self.ca_cert)
        if not self.proxies:
            self.session.impersonate = "safari"
        if self.user_agent and not browser_user_agent.match(self.user_agent):
            log.warning(
                f"ZipRecruiter: user_agent '{self.user_agent}' isn't accepted "
                "by the site, using the default"
            )
        elif self.user_agent:
            self.session.headers["user-agent"] = self.user_agent
        params = self._search_params()
        job_list: list[JobPost] = []
        seen = set()
        first_page = page = scraper_input.offset // jobs_per_page + 1
        skip = scraper_input.offset % jobs_per_page

        while len(job_list) < scraper_input.results_wanted:
            if page > first_page:
                time.sleep(random.uniform(self.delay, self.delay + self.band_delay))
            log.info(f"search page: {page}")
            try:
                # /jobs-search/1 redirects to /jobs-search
                path = "/jobs-search" if page == 1 else f"/jobs-search/{page}"
                response = self.session.get(self.base_url + path, params=params)
                if response.status_code != 200:
                    log.error(
                        f"ZipRecruiter response status code {response.status_code}"
                    )
                    break
                jobs, job_count = page_values(response.text, "jobKeysMap", "jobCount")
                last_page = math.ceil(job_count / jobs_per_page)
                new_jobs = [job for key, job in jobs.items() if key not in seen]
                seen.update(jobs)
            except Exception as e:
                log.error(f"ZipRecruiter: {e}")
                break

            for job in new_jobs[skip if page == first_page else 0 :]:
                try:
                    job_post = self._process_job(job)
                except Exception as e:
                    log.warning(f"skipping job: {e}")
                    continue
                if job_post:
                    job_list.append(job_post)
                    if len(job_list) >= scraper_input.results_wanted:
                        break

            if not new_jobs or page >= last_page:
                break
            page += 1

        return JobResponse(jobs=job_list)

    def _search_params(self) -> dict:
        search_term = self.scraper_input.search_term
        job_type = self.scraper_input.job_type
        if job_type == JobType.INTERNSHIP:
            if "internship" not in (search_term or "").lower():
                search_term = f"{search_term or ''} internship".strip()
        elif job_type and job_type not in job_type_codes:
            log.warning(
                f"ZipRecruiter: job_type {job_type.value[0]} isn't supported, "
                "ignoring it"
            )
        params = {
            "search": search_term,
            "location": self.scraper_input.location,
            "radius": self.scraper_input.distance,
        }
        if hours_old := self.scraper_input.hours_old:
            params["days"] = math.ceil(hours_old / 24)
        if code := job_type_codes.get(job_type):
            params["refine_by_employment"] = code
        if self.scraper_input.is_remote:
            params["refine_by_location_type"] = "only_remote"
        if self.scraper_input.easy_apply:
            params["refine_by_apply_type"] = "has_zipapply"
        return {name: value for name, value in params.items() if value}

    def _process_job(self, job: dict) -> JobPost | None:
        posted = datetime.fromisoformat(
            job["status"]["postedAtUtc"].replace("Z", "+00:00")
        )
        hours_old = self.scraper_input.hours_old
        if hours_old and posted.timestamp() < time.time() - hours_old * 3600:
            return None
        job_type = self._parse_job_type(job["employmentTypes"])
        if self.scraper_input.job_type == JobType.INTERNSHIP and (
            JobType.INTERNSHIP not in (job_type or [])
        ):
            return None

        location = job["location"]
        country = Country.CANADA if location["countryCode"] == "CA" else Country.USA
        apply_url = job["applyButtonConfig"].get("externalApplyUrl")
        job_post = JobPost(
            id=f"zr-{job['listingKey']}",
            title=job["title"],
            company_name=job["company"]["name"],
            company_url=self.base_url + job["companyUrl"]
            if job["companyUrl"]
            else None,
            company_logo=(job.get("companyLogo") or {}).get("logoUrl"),
            location=Location(
                city=location.get("city"),
                state=location.get("stateCode"),
                country=country,
            ),
            job_url=self.base_url + job["rawCanonicalZipJobPageUrl"],
            job_url_direct=direct_url(apply_url) if apply_url else None,
            date_posted=posted.date(),
            job_type=job_type,
            # REMOTE or REMOTE_OPTIONAL
            is_remote=any("REMOTE" in t["name"] for t in job["locationTypes"]),
            compensation=self._parse_salary(job["pay"]),
        )
        if self.scraper_input.fetch_description:
            details = self._fetch_details(job["listingKey"], job_post.job_url)
            job_post = job_post.model_copy(update=details)
        return job_post

    @staticmethod
    def _parse_job_type(types: list[dict]) -> list[JobType] | None:
        names = (t["name"].split("NAME_")[1].replace("_", "").lower() for t in types)
        return [t for name in names if (t := get_enum_from_job_type(name))] or None

    @staticmethod
    def _parse_salary(pay: dict) -> Compensation | None:
        if not pay.get("metadata", {}).get("visible"):
            return None
        return Compensation(
            interval=pay_intervals.get(pay["interval"]),
            min_amount=pay["min"],
            max_amount=pay["max"],
            currency=pay["currency"].removeprefix("PAY_CURRENCY_"),
        )

    def _fetch_details(self, job_id: str, job_url: str) -> dict:
        try:
            response = self.session.get(job_url, allow_redirects=True)
            if response.status_code != 200:
                log.warning(
                    f"ZipRecruiter response status code {response.status_code} "
                    f"for job {job_id}"
                )
                return {}
            [job] = page_values(response.text, "jobDetails")
            description, emails = format_description(
                job["htmlFullDescription"], self.scraper_input.description_format
            )
        except Exception as e:
            log.warning(f"ZipRecruiter: job {job_id}: {e}")
            return {}

        company = job.get("companyWidget") or {}
        reviews = job.get("breakroomCompany") or {}
        industries = company.get("canonicalIndustries")
        website = company.get("canonicalWebsite")
        rating = reviews.get("rating")
        return {
            "description": description or None,
            "emails": emails,
            "company_industry": industries[0] if industries else None,
            "company_url_direct": f"https://{website}" if website else None,
            "company_num_employees": company.get("companySizeDisplay"),
            "company_addresses": company.get("hqLocation"),
            "company_description": company.get("about") or reviews.get("description"),
            "company_rating": round(rating / 2, 2) if rating else None,
        }
