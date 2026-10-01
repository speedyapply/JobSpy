from __future__ import annotations

import math
import random
import re
import time
from datetime import datetime

from jobspy.bdjobs.constant import (
    description_sections,
    job_type_codes,
    job_types,
    jobs_per_page,
    locations,
    search_params,
)
from jobspy.model import (
    Compensation,
    CompensationInterval,
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
    markdown_converter,
    plain_converter,
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
        super().__init__(Site.BDJOBS, proxies=proxies, ca_cert=ca_cert)
        self.scraper_input = None
        self.session = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.session = create_session(
            proxies=self.proxies, ca_cert=self.ca_cert, is_tls=False, has_retry=True
        )
        params = self._search_params()
        job_list: list[JobPost] = []
        first_page = page = scraper_input.offset // jobs_per_page + 1
        skip = scraper_input.offset % jobs_per_page

        while len(job_list) < scraper_input.results_wanted:
            if page > first_page:
                time.sleep(random.uniform(self.delay, self.delay + self.band_delay))
            log.info(f"search page: {page}")
            try:
                response = self.session.get(
                    self.search_url,
                    params=params | {"pg": page},
                    timeout=scraper_input.request_timeout,
                )
                if response.status_code != 200:
                    log.error(f"BDJobs response status code {response.status_code}")
                    break
                result = response.json()
                jobs = list(result["data"])
                last_page = int(result["common"]["totalpages"])
            except Exception as e:
                log.error(f"BDJobs: {e}")
                break

            for job in jobs[skip if page == first_page else 0 :]:
                try:
                    job_post = self._process_job(job)
                except Exception as e:
                    log.warning(f"skipping job: {e}")
                    continue
                if job_post:
                    job_list.append(job_post)
                    if len(job_list) >= scraper_input.results_wanted:
                        break

            if not jobs or page >= last_page:
                break
            page += 1

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
            # the site counts calendar days in Bangladesh, today included, up to 5
            days = math.ceil(hours_old / 24) + 1
            if days <= 5:
                params["postedWithin"] = days
        if code := job_type_codes.get(self.scraper_input.job_type):
            params["jobNature"] = code
        if self.scraper_input.is_remote:
            params["workplace"] = 1
        return params

    def _process_job(self, job: dict) -> JobPost | None:
        posted = datetime.fromisoformat(job["publishDate"].replace("Z", "+00:00"))
        hours_old = self.scraper_input.hours_old
        if hours_old and posted.timestamp() < time.time() - hours_old * 3600:
            return None

        job_id = job["Jobid"]
        details = {}
        if self.scraper_input.fetch_description:
            details = self._fetch_details(job_id)

        city = job["location"].replace("Anywhere in Bangladesh", "").strip(", ")
        return JobPost(
            id=f"bd-{job_id}",
            title=job["jobTitle"],
            company_name=job["companyName"],
            location=Location(city=city or None, country=Country.BANGLADESH),
            job_url=f"{self.base_url}/h/details/{job_id}",
            date_posted=posted.date(),
            job_type=self._parse_job_type(job["JobType"]),
            is_remote="Home" in (job["WorkPlace"] or ""),
            compensation=self._parse_salary(job["Salary"]),
            company_logo=job["logoUrl"] or None,
            vacancy_count=job["Vacancies"],
            experience_range=job["experience"] if job["experience"] != "NA" else None,
            emails=extract_emails_from_text(details.get("description")),
            **details,
        )

    @staticmethod
    def _parse_job_type(text: str | None) -> list[JobType] | None:
        types = [job_types[t] for t in (text or "").split(",") if t in job_types]
        return types or None

    @staticmethod
    def _parse_salary(text: str | None) -> Compensation | None:
        match = re.fullmatch(r"Tk\. (\d+)(?: - (\d+))? \(Monthly\)", text or "")
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
                timeout=self.scraper_input.request_timeout,
            )
            details = response.json()["data"][0]
        except Exception:
            return {}

        description = "".join(
            f"<h4>{heading}</h4>{details[field]}"
            for heading, field in description_sections
            if details.get(field)
        )
        if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
            description = markdown_converter(description)
        elif self.scraper_input.description_format == DescriptionFormat.PLAIN:
            description = plain_converter(description)
        skills = details.get("SkillsRequired")
        return {
            "description": description or None,
            "skills": skills.split(", ") if skills else None,
            "company_addresses": details.get("CompanyAddress") or None,
            "company_description": details.get("CompanyBusiness") or None,
        }
