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
from jobspy.bdjobs.model import Job, JobDetails, JobSearch
from jobspy.model import (
    Compensation,
    CompensationInterval,
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
    too_old,
)


class BDJobs(Scraper):
    base_url = "https://bdjobs.com"
    search_url = "https://api.bdjobs.com/Jobs/api/JobSearch/GetJobSearch"
    details_url = "https://gateway.bdjobs.com/jobapply/api/JobSubsystem/Job-Details"
    delay = (2, 5)

    def scrape(self, scraper_input: ScraperInput) -> list[JobPost]:
        self.scraper_input = scraper_input
        self.session = create_session(
            RequestsRotating(scraper_input.proxies), scraper_input
        )
        params = self._search_params()
        job_list: list[JobPost] = []
        seen = set()
        page, skip = 1, scraper_input.offset

        while len(job_list) < scraper_input.results_wanted:
            if page > 1:
                time.sleep(random.uniform(*self.delay))
            self.log.info(f"search page: {page}")
            try:
                response = self.session.get(
                    self.search_url,
                    params=params | {"pg": page},
                )
                check_status(response)
                result = JobSearch.model_validate(response.json())
                jobs = result.data
                if page == 1:
                    jobs = (result.premiumData or []) + jobs
                last_page = result.totalpages
                new_jobs = []
                for job in jobs:
                    if job.get("Jobid") not in seen:
                        seen.add(job.get("Jobid"))
                        new_jobs.append(job)
            except Exception as e:
                self.fail(str(e))
                break

            for job in new_jobs[skip:]:
                try:
                    job_post = self._process_job(job)
                except Exception as e:
                    self.log.warning(f"skipping job: {e}")
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

        return job_list

    def _search_params(self) -> dict[str, str | int]:
        params = search_params | {"keyword": self.scraper_input.search_term or ""}
        place = (self.scraper_input.location or "").split(",")[0].strip().lower()
        if place in locations:
            params["location"] = locations[place]
        elif place and place != "bangladesh":
            self.warn(
                f"location '{self.scraper_input.location}' not found, "
                "searching all of Bangladesh"
            )
        if hours_old := self.scraper_input.hours_old:
            params["postedWithin"] = math.ceil(hours_old / 24) + 1
        job_type = self.scraper_input.job_type
        if job_type in job_type_codes:
            params["jobNature"] = job_type_codes[job_type]
        elif job_type:
            self.warn(f"job_type {job_type.value} isn't supported, ignoring it")
        if self.scraper_input.is_remote:
            params["workplace"] = 1
        if self.scraper_input.easy_apply:
            self.warn("easy_apply isn't supported, ignoring it")
        return params

    def _process_job(self, raw: dict[str, object]) -> JobPost | None:
        job = Job.model_validate(raw)
        posted = datetime.fromisoformat(job.publishDate.replace("Z", "+00:00"))
        if too_old(posted.timestamp(), self.scraper_input.hours_old):
            return None
        is_remote = job.WorkPlace == "Home"
        if self.scraper_input.is_remote and not is_remote:
            return None

        job_id = job.Jobid
        fetch = self.scraper_input.fetch_description
        details = self._fetch_details(job_id) if fetch else {}

        city = (job.location or "").replace("Anywhere in Bangladesh", "").strip(", ")
        return JobPost(
            id=f"bd-{job_id}",
            title=job.jobTitle,
            company=job.companyName,
            location=Location(city=city or None, country="Bangladesh"),
            job_url=f"{self.base_url}/h/details/{job_id}",
            date_posted=posted.date(),
            job_type=self._parse_job_type(job.JobType),
            is_remote=is_remote,
            **self._parse_salary(job.Salary).model_dump(),
            company_logo=job.logoUrl or None,
            vacancy_count=job.Vacancies,
            experience_range=job.experience if job.experience != "NA" else None,
        ).model_copy(update=details)

    @staticmethod
    def _parse_job_type(text: str) -> list[JobType] | None:
        labels = text.split(",")
        return [job_type_labels[t] for t in labels if t in job_type_labels] or None

    @staticmethod
    def _parse_salary(text: str) -> Compensation:
        match = re.fullmatch(r"Tk\. (\d+)(?: - (\d+))? \(Monthly\)", text)
        if not match:
            return Compensation()
        low, high = match.groups()
        return Compensation(
            interval=CompensationInterval.MONTHLY,
            min_amount=float(low),
            max_amount=float(high or low),
            currency="BDT",
        )

    def _fetch_details(self, job_id: str) -> dict[str, object]:
        try:
            response = self.session.get(
                self.details_url,
                params={"jobId": job_id, "ln": "1", "IsCorporate": "false"},
            )
            check_status(response)
            result = JobDetails.model_validate(response.json())
            if not result.data:
                self.warn(f"job {job_id}: {result.message}")
                return {}
            details = result.data[0]
            fields = description_fields(
                "".join(
                    f"<h4>{heading}</h4>{getattr(details, field)}"
                    for heading, field in description_sections
                    if getattr(details, field)
                ),
                self.scraper_input.description_format,
            )
            skills = details.SkillsRequired
            company_id = details.CompanyID
            company_url = None
            if company_id != "0" and not details.HaveAliasName:
                company_url = f"{self.base_url}/h/company-insight/{company_id}"
            website = details.CompanyWeb.strip()
            if " " in website:
                website = ""
            elif website and not website.startswith("http"):
                website = f"https://{website}"
            apply_link = re.search(r"href='([^']+)", details.ApplyURL)
            apply_url = apply_link.group(1) if apply_link else None
            host = urlparse(apply_url or "").hostname or ""
            if host == "bdjobs.com" or host.endswith(".bdjobs.com"):
                apply_url = None
            return {
                **fields,
                "skills": skills.split(", ") if skills else None,
                "job_url_direct": apply_url,
                "company_url": company_url,
                "company_url_direct": website or None,
                "company_addresses": details.CompanyAddress or None,
                "company_description": details.CompanyBusiness or None,
            }
        except Exception as e:
            self.warn(f"job {job_id}: {e}")
            return {}
