from __future__ import annotations

import math
import random
import time
from datetime import datetime

from jobspy.model import (
    Compensation,
    Country,
    DescriptionFormat,
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
    extract_emails_from_text,
    get_enum_from_job_type,
    markdown_converter,
    plain_converter,
)
from jobspy.ziprecruiter.constant import job_type_codes, jobs_per_page, pay_intervals
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
        super().__init__(Site.ZIP_RECRUITER, proxies=proxies, ca_cert=ca_cert)
        self.scraper_input = None
        self.session = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.session = create_session(proxies=self.proxies, ca_cert=self.ca_cert)
        if not self.proxies:
            self.session.impersonate = "safari"
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
        params = {
            "search": self.scraper_input.search_term,
            "location": self.scraper_input.location,
            "radius": self.scraper_input.distance,
        }
        if hours_old := self.scraper_input.hours_old:
            params["days"] = math.ceil(hours_old / 24)
        if code := job_type_codes.get(self.scraper_input.job_type):
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

        job_url = self.base_url + job["rawCanonicalZipJobPageUrl"]
        details = {}
        if self.scraper_input.fetch_description:
            details = self._fetch_details(job_url)

        location = job["location"]
        country = Country.CANADA if location["countryCode"] == "CA" else Country.USA
        apply_url = job["applyButtonConfig"].get("externalApplyUrl")
        return JobPost(
            id=f"zr-{job['listingKey']}",
            title=job["title"],
            company_name=job["company"]["name"],
            company_url=self.base_url + job["companyUrl"],
            company_logo=(job.get("companyLogo") or {}).get("logoUrl"),
            location=Location(
                city=location.get("city"),
                state=location["stateCode"],
                country=country,
            ),
            job_url=job_url,
            job_url_direct=direct_url(apply_url) if apply_url else None,
            date_posted=posted.date(),
            job_type=self._parse_job_type(job["employmentTypes"]),
            # REMOTE or REMOTE_OPTIONAL
            is_remote=any("REMOTE" in t["name"] for t in job["locationTypes"]),
            compensation=self._parse_salary(job["pay"]),
            emails=extract_emails_from_text(details.get("description")),
            **details,
        )

    @staticmethod
    def _parse_job_type(types: list[dict]) -> list[JobType] | None:
        names = (t["name"].split("NAME_")[1].replace("_", "").lower() for t in types)
        return [t for name in names if (t := get_enum_from_job_type(name))] or None

    @staticmethod
    def _parse_salary(pay: dict) -> Compensation | None:
        # hidden pay is the site's own estimate
        if not pay.get("metadata", {}).get("visible"):
            return None
        return Compensation(
            interval=pay_intervals.get(pay["interval"]),
            min_amount=pay["min"],
            max_amount=pay["max"],
            currency=pay["currency"].removeprefix("PAY_CURRENCY_"),
        )

    def _fetch_details(self, job_url: str) -> dict:
        try:
            response = self.session.get(job_url, allow_redirects=True)
            [job] = page_values(response.text, "jobDetails")
            description = job["htmlFullDescription"]
        except Exception:
            return {}

        if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
            description = markdown_converter(description)
        elif self.scraper_input.description_format == DescriptionFormat.PLAIN:
            description = plain_converter(description)
        company = job.get("companyWidget") or {}
        industries = company.get("canonicalIndustries")
        website = company.get("canonicalWebsite")
        return {
            "description": description or None,
            "company_industry": industries[0] if industries else None,
            "company_url_direct": f"https://{website}" if website else None,
            "company_num_employees": company.get("companySizeDisplay"),
            "company_addresses": company.get("hqLocation"),
        }
