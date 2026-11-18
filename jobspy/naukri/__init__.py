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
    place_levels,
    place_params,
    search_params,
)
from jobspy.naukri.model import (
    Job,
    JobDetails,
    JobSearch,
    Places,
    Row,
    Salary,
    Shared,
)
from jobspy.naukri.util import generate_nkparam
from jobspy.util import (
    TLSRotating,
    check_status,
    create_session,
    description_fields,
    plain_converter,
    too_old,
    utc_date,
)


class Naukri(Scraper):
    base_url = "https://www.naukri.com"
    search_url = f"{base_url}/jobapi/v3/search"
    job_page_url = f"{base_url}/jobapi/v4/job"
    places_url = "https://taxonomy-suggest.naukri.com/suggest/taxonomyCommonSuggester"
    delay = (3, 7)

    def scrape(self, scraper_input: ScraperInput) -> list[JobPost]:
        self.scraper_input = scraper_input
        self.session = create_session(TLSRotating(scraper_input.proxies), scraper_input)
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
                response = self.session.get(
                    self.search_url,
                    params=params | {"pageNo": page},
                    headers=headers | {"nkparam": generate_nkparam("srp")},
                )
                if response.status_code == 400 and page > 1:
                    break  # past the last page
                if response.status_code == 406:
                    self.fail(
                        "response status code 406 (recaptcha required): "
                        "the address is rate limited, or the request token was "
                        "rejected (the public key in jobspy/naukri/constant.py "
                        "may be out of date)"
                    )
                    break
                check_status(response)
                result = JobSearch.model_validate(response.json())
                jobs = result.jobDetails or []
                last_page = math.ceil(result.noOfJobs / jobs_per_page)
                new_jobs = [job for job in jobs if job.get("jobId") not in seen]
                seen.update(job.get("jobId") for job in jobs)
            except Exception as e:
                self.fail(str(e))
                break

            fresh = False
            for job in new_jobs[skip if page == first_page else 0 :]:
                try:
                    posted = Row.model_validate(job).createdDate / 1000
                    if too_old(posted, scraper_input.hours_old):
                        continue
                    fresh = True
                    job_post = self._process_job(job)
                except Exception as e:
                    self.log.warning(f"skipping job: {e}")
                    continue
                if job_post:
                    job_list.append(job_post)
                    if len(job_list) >= scraper_input.results_wanted:
                        break

            if not fresh or page >= last_page:
                break
            page += 1

        return job_list

    def _search_params(self) -> dict[str, str | int]:
        params = search_params | {"keyword": self.scraper_input.search_term or ""}
        job_type = self.scraper_input.job_type
        if job_type == JobType.INTERNSHIP:
            params |= internship_params
        elif job_type:
            self.warn(f"job_type {job_type.value} isn't supported, ignoring it")
        if location := self._location():
            params["location"] = location
        if hours_old := self.scraper_input.hours_old:
            params |= {"jobAge": math.ceil(hours_old / 24), "sort": "f"}
        if self.scraper_input.is_remote:
            params["wfhType"] = 2
        return params

    def _location(self) -> str | None:
        location = self.scraper_input.location
        parts = [part.strip() for part in (location or "").split(",")]
        places = list(dict.fromkeys(filter(None, parts)))
        if len(places) < 2:
            return location
        try:
            levels = {place: self._place_level(place) for place in places}
        except Exception as e:
            self.warn(f"location '{location}' not looked up, searching each place: {e}")
            return location
        finally:
            self.session.cookies.clear()
        narrowest = max((n for n in levels.values() if n is not None), default=None)
        return ", ".join(p for p in places if levels[p] in (None, narrowest))

    def _place_level(self, place: str) -> int | None:
        response = self.session.get(
            self.places_url, params=place_params | {"query": place, "astext": place}
        )
        check_status(response)
        return max(
            (
                place_levels[match.type]
                for match in Places.model_validate(response.json()).title
                if match.type in place_levels
                and place.lower() in map(str.lower, match.name)
            ),
            default=None,
        )

    def _process_job(self, raw: dict[str, object]) -> JobPost | None:
        job = Job.model_validate(raw)
        if self.scraper_input.easy_apply and job.companyApplyJob:
            return None

        job_id = job.jobId
        posted = job.createdDate / 1000
        details = self._shared_fields(job)
        if self.scraper_input.fetch_description:
            posted, page = self._fetch_details(job_id) or (posted, {})
            if too_old(posted, self.scraper_input.hours_old):
                return None
            details |= {name: value for name, value in page.items() if value}

        labels = {label.type: label.label for label in job.placeholders}
        # e.g. "Hybrid - Pune, Bengaluru", "Remote", "India"
        work_mode, _, city = labels["location"].rpartition(" - ")
        if city == "Remote":
            work_mode = "Remote"

        return JobPost(
            id=f"nk-{job_id}",
            title=job.title,
            company=job.companyName,
            company_url=f"{self.base_url}/{job.staticUrl}" if job.staticUrl else None,
            location=Location(
                city=None if city in ("Remote", "India") else city,
                country=Country.INDIA,
            ),
            job_url=self.base_url + job.jdURL,
            date_posted=utc_date(posted),
            is_remote=work_mode == "Remote",
            work_from_home_type=work_mode or "Work from office",
            **self._parse_salary(job.salaryDetail, labels["salary"]).model_dump(),
            company_logo=job.logoPathV3,
            skills=job.tagsAndSkills.split(",") if job.tagsAndSkills else None,
            experience_range=job.experienceText,
            company_rating=job.AggregateRating,
            company_reviews_count=job.ReviewsCount,
        ).model_copy(update=details)

    @staticmethod
    def _shared_fields(job: Shared) -> dict[str, object]:
        """The fields a search row and a job page both carry."""
        if job.jobType == "internship":
            job_type = [JobType.INTERNSHIP]
        elif job.employmentType is None:
            raise ValueError("no employment type")
        else:
            parts = job.employmentType.split(", ")
            job_type = [
                job_type_labels[part] for part in parts if part in job_type_labels
            ]
        return {
            "job_type": job_type or None,
            "vacancy_count": job.vacancy or None,
            "job_url_direct": job.applyRedirectUrl or None,
        }

    @staticmethod
    def _parse_salary(salary: Salary, label: str) -> Compensation:
        if not salary.hideSalary:
            return Compensation(
                interval=CompensationInterval.YEARLY,
                min_amount=salary.minimumSalary,
                max_amount=salary.maximumSalary,
                currency=salary.currency,
            )
        if stipend := re.fullmatch(r"([\d,]+)/month", label):
            amount = float(stipend[1].replace(",", ""))
            return Compensation(
                interval=CompensationInterval.MONTHLY,
                min_amount=amount,
                max_amount=amount,
                currency="INR",
            )
        return Compensation()

    def _fetch_details(self, job_id: str) -> tuple[float, dict[str, object]] | None:
        try:
            response = self.session.get(
                f"{self.job_page_url}/{job_id}",
                headers=job_page_headers | {"nkparam": generate_nkparam(job_id)},
            )
            if response.status_code == 406:
                raise ValueError("response status code 406: rate limited")
            check_status(response)
            job = JobDetails.model_validate(response.json()["jobDetails"])
            posted = datetime.strptime(job.createdDate, "%Y-%m-%d %H:%M:%S")
            fields = description_fields(
                job.description, self.scraper_input.description_format
            )
            details = self._shared_fields(job) | {
                **fields,
                "company_industry": job.industry,
                "job_function": job.functionalArea,
                "company_description": plain_converter(job.details),
                "company_addresses": job.address or None,
            }
            return posted.replace(tzinfo=india_time).timestamp(), details
        except Exception as e:
            self.log.warning(f"job {job_id}: {e}")
            return None
