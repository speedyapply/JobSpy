from __future__ import annotations

import math
import random
import re
import time
from datetime import datetime
from urllib.parse import urlparse

from jobspy.bdjobs.constant import (
    description_sections,
    job_type_codes,
    job_type_labels,
    jobs_per_page,
    locations,
    search_params,
)
from jobspy.model import (
    Compensation,
    CompensationInterval,
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
)

log = create_logger("BDJobs")


class BDJobs(Scraper):
    base_url = "https://bdjobs.com"
    search_url = "https://api.bdjobs.com/Jobs/api/JobSearch/GetJobSearch"
    details_url = "https://gateway.bdjobs.com/jobapply/api/JobSubsystem/Job-Details"
    delay = 2
    band_delay = 3

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.BDJOBS, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent
        )
        self.scraper_input = None
        self.session = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.session = create_session(
            proxies=self.proxies, ca_cert=self.ca_cert, is_tls=False
        )
        if self.user_agent:
            self.session.headers["user-agent"] = self.user_agent
        params = self._search_params()
        job_list: list[JobPost] = []
        seen = set()
        page, skip = 1, scraper_input.offset

        while len(job_list) < scraper_input.results_wanted:
            if page > 1:
                time.sleep(random.uniform(self.delay, self.delay + self.band_delay))
            log.info(f"search page: {page}")
            try:
                response = self.session.get(
                    self.search_url,
                    params=params | {"pg": page},
                )
                if response.status_code != 200:
                    log.error(f"BDJobs response status code {response.status_code}")
                    break
                result = response.json()
                jobs = result["data"]
                if page == 1:
                    jobs = (result.get("premiumData") or []) + jobs
                last_page = int(result["common"]["totalpages"])
                new_jobs = []
                for job in jobs:
                    if job.get("Jobid") not in seen:
                        seen.add(job.get("Jobid"))
                        new_jobs.append(job)
            except Exception as e:
                log.error(f"BDJobs: {e}")
                break

            for job in new_jobs[skip:]:
                try:
                    job_post = self._process_job(job)
                except Exception as e:
                    log.warning(f"skipping job: {e}")
                    continue
                if job_post:
                    job_list.append(job_post)
                    if len(job_list) >= scraper_input.results_wanted:
                        break

            skip = max(skip - len(new_jobs), 0)
            page += 1 + skip // jobs_per_page
            skip %= jobs_per_page
            if not new_jobs or page > last_page:
                break

        return JobResponse(jobs=job_list)

    def _search_params(self) -> dict:
        params = search_params | {"keyword": self.scraper_input.search_term or ""}
        place = (self.scraper_input.location or "").split(",")[0].strip().lower()
        if place in locations:
            params["location"] = locations[place]
        elif place and place != "bangladesh":
            log.warning(
                f"BDJobs: location '{self.scraper_input.location}' not found, "
                "searching all of Bangladesh"
            )
        if hours_old := self.scraper_input.hours_old:
            params["postedWithin"] = math.ceil(hours_old / 24) + 1
        job_type = self.scraper_input.job_type
        if job_type in job_type_codes:
            params["jobNature"] = job_type_codes[job_type]
        elif job_type:
            log.warning(
                f"BDJobs: job_type {job_type.value[0]} isn't supported, ignoring it"
            )
        if self.scraper_input.is_remote:
            params["workplace"] = 1
        if self.scraper_input.easy_apply:
            log.warning("BDJobs: easy_apply isn't supported, ignoring it")
        return params

    def _process_job(self, job: dict) -> JobPost | None:
        posted = datetime.fromisoformat(job["publishDate"].replace("Z", "+00:00"))
        hours_old = self.scraper_input.hours_old
        if hours_old and posted.timestamp() < time.time() - hours_old * 3600:
            return None
        is_remote = job["WorkPlace"] == "Home"
        if self.scraper_input.is_remote and not is_remote:
            return None

        job_id = job["Jobid"]
        fetch = self.scraper_input.fetch_description
        details = self._fetch_details(job_id) if fetch else {}

        city = (job["location"] or "").replace("Anywhere in Bangladesh", "").strip(", ")
        return JobPost(
            id=f"bd-{job_id}",
            title=job["jobTitle"],
            company_name=job["companyName"],
            location=Location(city=city or None, country=Country.BANGLADESH),
            job_url=f"{self.base_url}/h/details/{job_id}",
            date_posted=posted.date(),
            job_type=self._parse_job_type(job["JobType"]),
            is_remote=is_remote,
            compensation=self._parse_salary(job["Salary"]),
            company_logo=job["logoUrl"] or None,
            vacancy_count=job["Vacancies"],
            experience_range=job["experience"] if job["experience"] != "NA" else None,
            **details,
        )

    @staticmethod
    def _parse_job_type(text: str) -> list[JobType] | None:
        labels = text.split(",")
        return [job_type_labels[t] for t in labels if t in job_type_labels] or None

    @staticmethod
    def _parse_salary(text: str) -> Compensation | None:
        match = re.fullmatch(r"Tk\. (\d+)(?: - (\d+))? \(Monthly\)", text)
        if not match:
            return None
        low, high = match.groups()
        return Compensation(
            interval=CompensationInterval.MONTHLY,
            min_amount=float(low),
            max_amount=float(high or low),
            currency="BDT",
        )

    def _fetch_details(self, job_id: str) -> dict:
        try:
            response = self.session.get(
                self.details_url,
                params={"jobId": job_id, "ln": 1, "IsCorporate": "false"},
            )
            if response.status_code != 200:
                log.warning(
                    f"BDJobs response status code {response.status_code} "
                    f"for job {job_id}"
                )
                return {}
            result = response.json()
            if not result["data"]:
                log.warning(f"BDJobs: job {job_id}: {result['message']}")
                return {}
            details = result["data"][0]
            description, emails = format_description(
                "".join(
                    f"<h4>{heading}</h4>{details[field]}"
                    for heading, field in description_sections
                    if details[field]
                ),
                self.scraper_input.description_format,
            )
            skills = details["SkillsRequired"]
            company_id = details["CompanyID"]
            company_url = None
            if company_id != "0" and not details["HaveAliasName"]:
                company_url = f"{self.base_url}/h/company-insight/{company_id}"
            website = details["CompanyWeb"].strip()
            if " " in website:
                website = ""
            elif website and not website.startswith("http"):
                website = f"https://{website}"
            apply_link = re.search(r"href='([^']+)", details["ApplyURL"])
            apply_url = apply_link.group(1) if apply_link else None
            host = urlparse(apply_url or "").hostname or ""
            if host == "bdjobs.com" or host.endswith(".bdjobs.com"):
                apply_url = None
            return {
                "description": description or None,
                "emails": emails,
                "skills": skills.split(", ") if skills else None,
                "job_url_direct": apply_url,
                "company_url": company_url,
                "company_url_direct": website or None,
                "company_addresses": details["CompanyAddress"] or None,
                "company_description": details["CompanyBusiness"] or None,
            }
        except Exception as e:
            log.warning(f"BDJobs: job {job_id}: {e}")
            return {}
