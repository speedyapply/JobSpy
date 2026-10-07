from __future__ import annotations

import math
import random
import re
import time
from datetime import datetime

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
)
from jobspy.naukri.constant import (
    headers,
    india_time,
    internship_params,
    job_page_headers,
    job_type_labels,
    jobs_per_page,
    search_params,
)
from jobspy.naukri.util import generate_nkparam
from jobspy.util import (
    create_logger,
    create_session,
    format_description,
    plain_converter,
    utc_date,
)

log = create_logger("Naukri")


class Naukri(Scraper):
    base_url = "https://www.naukri.com"
    search_url = f"{base_url}/jobapi/v3/search"
    job_page_url = f"{base_url}/jobapi/v4/job"
    delay = 3
    band_delay = 4

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.session = create_session(
            proxies=self.proxies, ca_cert=self.ca_cert, user_agent=self.user_agent
        )
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
                response = self.session.get(
                    self.search_url,
                    params=params | {"pageNo": page},
                    headers=headers | {"nkparam": generate_nkparam("srp")},
                )
                if response.status_code == 400 and page > 1:
                    break  # past the last page
                if response.status_code == 406:
                    log.error(
                        "Naukri response status code 406 (recaptcha required): "
                        "the address is rate limited, or the request token was "
                        "rejected (the public key in jobspy/naukri/constant.py "
                        "may be out of date)"
                    )
                    break
                if response.status_code != 200:
                    log.error(f"Naukri response status code {response.status_code}")
                    break
                result = response.json()
                jobs = result.get("jobDetails") or []
                last_page = math.ceil(result["noOfJobs"] / jobs_per_page)
                new_jobs = [job for job in jobs if job.get("jobId") not in seen]
                seen.update(job.get("jobId") for job in jobs)
            except Exception as e:
                log.error(f"Naukri: {e}")
                break

            fresh = False
            for job in new_jobs[skip if page == first_page else 0 :]:
                try:
                    if self._too_old(job["createdDate"] / 1000):
                        continue
                    fresh = True
                    job_post = self._process_job(job)
                except Exception as e:
                    log.warning(f"skipping job: {e}")
                    continue
                if job_post:
                    job_list.append(job_post)
                    if len(job_list) >= scraper_input.results_wanted:
                        break

            if not fresh or page >= last_page:
                break
            page += 1

        return JobResponse(jobs=job_list)

    def _search_params(self) -> dict:
        params = search_params | {"keyword": self.scraper_input.search_term or ""}
        job_type = self.scraper_input.job_type
        if job_type == JobType.INTERNSHIP:
            params |= internship_params
        elif job_type:
            log.warning(
                f"Naukri: job_type {job_type.value[0]} isn't supported, ignoring it"
            )
        if self.scraper_input.location:
            params["location"] = self.scraper_input.location
        if hours_old := self.scraper_input.hours_old:
            params |= {"jobAge": math.ceil(hours_old / 24), "sort": "f"}
        if self.scraper_input.is_remote:
            params["wfhType"] = 2
        return params

    def _too_old(self, posted: float) -> bool:
        """posted: epoch seconds, or 0 for a job whose age isn't known (kept)"""
        hours_old = self.scraper_input.hours_old
        return bool(hours_old and posted and posted < time.time() - hours_old * 3600)

    def _process_job(self, job: dict) -> JobPost | None:
        if self.scraper_input.easy_apply and job["companyApplyJob"]:
            return None

        job_id = job["jobId"]
        posted = job["createdDate"] / 1000
        details = self._shared_fields(job)
        if self.scraper_input.fetch_description:
            page = self._fetch_details(job_id)
            posted = page.pop("posted", posted)
            if self._too_old(posted):
                return None
            details |= {name: value for name, value in page.items() if value}

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
            date_posted=utc_date(posted),
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
            **details,
        )

    @staticmethod
    def _shared_fields(job: dict) -> dict:
        """The fields a search row and a job page both carry."""
        if job.get("jobType") == "internship":
            job_type = [JobType.INTERNSHIP]
        else:
            parts = job.get("employmentType", "").split(", ")
            job_type = [
                job_type_labels[part] for part in parts if part in job_type_labels
            ]
        return {
            "job_type": job_type or None,
            "vacancy_count": job.get("vacancy") or None,
            "job_url_direct": job.get("applyRedirectUrl") or None,
        }

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
            )
            if response.status_code != 200:
                reason = ": rate limited" if response.status_code == 406 else ""
                log.warning(
                    f"Naukri response status code {response.status_code} "
                    f"for job {job_id}{reason}"
                )
                return {}
            job = response.json()["jobDetails"]
            posted = datetime.strptime(job["createdDate"], "%Y-%m-%d %H:%M:%S")
            description, emails = format_description(
                job["description"], self.scraper_input.description_format
            )
            company = job["companyDetail"]
            return self._shared_fields(job) | {
                "description": description,
                "emails": emails,
                "posted": posted.replace(tzinfo=india_time).timestamp(),
                "company_industry": job["industry"],
                "job_function": job["functionalArea"],
                "company_description": plain_converter(company["details"]),
                "company_addresses": company["address"] or None,
            }
        except Exception as e:
            log.warning(f"Naukri: job {job_id}: {e}")
            return {}
