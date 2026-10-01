from __future__ import annotations

import math
import random
import re
import time
from datetime import date

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
from jobspy.naukri.constant import (
    headers,
    job_page_headers,
    jobs_per_page,
    search_params,
)
from jobspy.naukri.util import generate_nkparam
from jobspy.util import (
    create_logger,
    create_session,
    extract_emails_from_text,
    get_enum_from_job_type,
    markdown_converter,
    plain_converter,
)

log = create_logger("Naukri")


class Naukri(Scraper):
    base_url = "https://www.naukri.com"
    search_url = f"{base_url}/jobapi/v3/search"
    job_page_url = f"{base_url}/jobapi/v4/job"
    delay = 3
    band_delay = 4
    timeout = 10

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(Site.NAUKRI, proxies=proxies, ca_cert=ca_cert)
        self.scraper_input = None
        self.session = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.session = create_session(proxies=self.proxies, ca_cert=self.ca_cert)
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
                    params=params | {"pageNo": page},
                    headers=headers | {"nkparam": generate_nkparam("srp")},
                    timeout=self.timeout,
                )
                if response.status_code == 400 and page > 1:
                    break  # past the last page
                if response.status_code == 406:
                    log.error(
                        "Naukri rejected the request token (406); the public key in "
                        "jobspy/naukri/constant.py may be out of date"
                    )
                    break
                if response.status_code != 200:
                    log.error(f"Naukri response status code {response.status_code}")
                    break
                result = response.json()
                jobs = result.get("jobDetails") or []
                last_page = math.ceil(result["noOfJobs"] / jobs_per_page)
            except Exception as e:
                log.error(f"Naukri: {e}")
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
        keyword = self.scraper_input.search_term or ""
        if self.scraper_input.job_type == JobType.INTERNSHIP:
            # Naukri has no job type filter
            keyword = f"{keyword} internship".strip()
        params = search_params | {"keyword": keyword}
        if self.scraper_input.location:
            params["location"] = self.scraper_input.location
        if hours_old := self.scraper_input.hours_old:
            # jobAge=N covers today plus N earlier days
            params["jobAge"] = math.ceil(hours_old / 24)
        if self.scraper_input.is_remote:
            params["wfhType"] = 2
        return params

    def _process_job(self, job: dict) -> JobPost | None:
        posted = job["createdDate"] / 1000  # 0 for internships
        hours_old = self.scraper_input.hours_old
        if hours_old and posted and posted < time.time() - hours_old * 3600:
            return None
        if self.scraper_input.easy_apply and job["companyApplyJob"]:
            return None
        internships = self.scraper_input.job_type == JobType.INTERNSHIP
        if internships and job.get("jobType") != "internship":
            return None

        job_id = job["jobId"]
        details = {
            "job_type": self._parse_job_type(job.get("jobType")),
            "vacancy_count": job.get("vacancy"),
        }
        if self.scraper_input.fetch_description:
            details |= self._fetch_details(job_id)

        labels = {label["type"]: label["label"] for label in job["placeholders"]}
        # e.g. "Hybrid - Pune, Bengaluru", "Remote", "India"
        work_mode, _, city = labels["location"].rpartition(" - ")
        if city == "Remote":
            work_mode = "Remote"
        if city in ("Remote", "India"):
            city = None
        rating = job.get("ambitionBoxData") or {}

        return JobPost(
            id=f"nk-{job_id}",
            title=job["title"],
            company_name=job["companyName"],
            company_url=f"{self.base_url}/{job['staticUrl']}",
            location=Location(city=city, country=Country.INDIA),
            job_url=self.base_url + job["jdURL"],
            date_posted=date.fromtimestamp(posted) if posted else None,
            is_remote=work_mode == "Remote",
            work_from_home_type=work_mode or "Work from office",
            compensation=self._parse_salary(job["salaryDetail"], labels["salary"]),
            company_logo=job["logoPathV3"],
            skills=(
                job["tagsAndSkills"].split(",") if job.get("tagsAndSkills") else None
            ),
            experience_range=job.get("experienceText"),
            company_rating=rating.get("AggregateRating"),
            company_reviews_count=rating.get("ReviewsCount"),
            emails=extract_emails_from_text(details.get("description")),
            **details,
        )

    @staticmethod
    def _parse_job_type(text: str | None) -> list[JobType] | None:
        job_type = get_enum_from_job_type(text or "")
        return [job_type] if job_type else None

    @staticmethod
    def _parse_salary(salary: dict, label: str) -> Compensation | None:
        if not salary["hideSalary"]:
            return Compensation(
                interval=CompensationInterval.YEARLY,
                min_amount=salary["minimumSalary"],
                max_amount=salary["maximumSalary"],
                currency=salary["currency"],
            )
        if stipend := re.fullmatch(r"([\d,]+)/month", label):
            amount = float(stipend[1].replace(",", ""))
            return Compensation(
                interval=CompensationInterval.MONTHLY,
                min_amount=amount,
                max_amount=amount,
                currency="INR",
            )
        return None

    def _fetch_details(self, job_id: str) -> dict:
        try:
            response = self.session.get(
                f"{self.job_page_url}/{job_id}",
                headers=job_page_headers | {"nkparam": generate_nkparam(job_id)},
                timeout=self.timeout,
            )
            job = response.json()["jobDetails"]
        except Exception:
            return {}

        description = job.get("description")
        if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
            description = markdown_converter(description)
        elif self.scraper_input.description_format == DescriptionFormat.PLAIN:
            description = plain_converter(description)
        company = job.get("companyDetail") or {}
        return {
            "description": description or None,
            "job_type": self._parse_job_type(job.get("jobType")),
            "vacancy_count": job.get("vacancy"),
            "job_url_direct": job.get("applyRedirectUrl") or None,
            "company_industry": job.get("industry") or None,
            "job_function": job.get("functionalArea") or None,
            "company_description": plain_converter(company.get("details")) or None,
            "company_addresses": company.get("address") or None,
        }
