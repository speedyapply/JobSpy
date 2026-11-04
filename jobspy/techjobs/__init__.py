from __future__ import annotations

import math
import re
import time
import unicodedata
from datetime import datetime

from pydantic import BaseModel

from jobspy.model import Country, JobPost, Location, Scraper, ScraperInput
from jobspy.techjobs.constant import (
    city_names,
    city_slugs,
    job_types,
    jobs_per_page,
    max_posted_within_days,
    remote_slugs,
)
from jobspy.util import RequestsRotating, check_status, create_session, too_old


class FeedJob(BaseModel):
    id: int
    title: str
    company: str
    company_slug: str
    location: str | None = None
    cities: list[str] = []
    workplace_type: str | None = None
    employment_type: str | None = None
    seniority: str | None = None
    skills: list[str] = []
    posted_at: str | None = None
    apply_url: str
    url: str
    summary: str | None = None


class FeedPage(BaseModel):
    total: int
    pages: int
    jobs: list[FeedJob]


class TechJobs(Scraper):
    """techjobs.vn: tech jobs in Vietnam, crawled hourly from each employer's own
    careers page or ATS. Reads its public JSON feed; no HTML scraping."""

    base_url = "https://techjobs.vn"
    feed_url = f"{base_url}/feeds/jobs.json"
    delay = 2  # robots.txt Crawl-delay

    def scrape(self, scraper_input: ScraperInput) -> list[JobPost]:
        self.scraper_input = scraper_input
        self.session = create_session(
            RequestsRotating(scraper_input.proxies), scraper_input
        )
        params = self._search_params()
        job_list: list[JobPost] = []
        first_page = page = scraper_input.offset // jobs_per_page + 1
        skip = scraper_input.offset % jobs_per_page

        while len(job_list) < scraper_input.results_wanted:
            if page > first_page:
                time.sleep(self.delay)
            self.log.info(f"search page: {page}")
            try:
                response = self.session.get(
                    self.feed_url,
                    params=params | {"page": page, "per_page": jobs_per_page},
                    timeout=30,
                )
                check_status(response)
                feed = FeedPage.model_validate(response.json())
            except Exception as e:
                self.fail(str(e))
                break

            for job in feed.jobs[skip:]:
                job_post = self._process_job(job)
                if job_post:
                    job_list.append(job_post)
                    if len(job_list) >= scraper_input.results_wanted:
                        break
            skip = 0
            if page >= feed.pages:
                break
            page += 1

        return job_list

    def _search_params(self) -> dict[str, str | int]:
        scraper_input = self.scraper_input
        params: dict[str, str | int] = {}
        if scraper_input.search_term:
            params["q"] = scraper_input.search_term
        if scraper_input.is_remote:
            params["city"] = "remote"
            if scraper_input.location:
                self.warn("is_remote searches remote jobs only, ignoring location")
        elif scraper_input.location:
            city = city_slugs.get(self._normalize(scraper_input.location))
            if city:
                params["city"] = city
            else:
                self.warn(
                    f"location {scraper_input.location!r} isn't a city techjobs knows, "
                    "searching all of Vietnam"
                )
        if scraper_input.hours_old:
            days = math.ceil(scraper_input.hours_old / 24)
            params["posted_within_days"] = min(max(days, 1), max_posted_within_days)
        if scraper_input.easy_apply:
            self.warn("easy_apply isn't supported, ignoring it")
        return params

    @staticmethod
    def _normalize(text: str) -> str:
        """ "Hồ Chí Minh City" -> "ho chi minh city"; "Đà Nẵng" -> "da nang" """
        text = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
        text = "".join(c for c in text if not unicodedata.combining(c)).lower()
        text = re.sub(r"[^a-z0-9]+", " ", text).strip()
        return re.sub(r"(,? ?(viet ?nam|vn))$", "", text).strip()

    def _process_job(self, job: FeedJob) -> JobPost | None:
        posted = datetime.fromisoformat(job.posted_at) if job.posted_at else None
        if posted and too_old(posted.timestamp(), self.scraper_input.hours_old):
            return None
        job_type = job_types.get((job.employment_type or "").lower())
        wanted = self.scraper_input.job_type
        if wanted and job_type != wanted:
            return None
        is_remote = job.workplace_type == "remote" or bool(
            remote_slugs & set(job.cities)
        )
        if self.scraper_input.is_remote and not is_remote:
            return None
        return JobPost(
            id=f"tj-{job.id}",
            title=job.title,
            company=job.company,
            company_url=f"{self.base_url}/companies/{job.company_slug}",
            location=self._location(job),
            job_url=job.url,
            job_url_direct=job.apply_url,
            date_posted=posted.date() if posted else None,
            job_type=[job_type] if job_type else None,
            is_remote=is_remote,
            job_level=job.seniority if job.seniority != "unknown" else None,
            skills=job.skills or None,
            description=job.summary if self.scraper_input.fetch_description else None,
        )

    @staticmethod
    def _location(job: FeedJob) -> Location | None:
        city = next(
            (city_names[slug] for slug in job.cities if slug in city_names), None
        )
        if city:
            return Location(city=city, country=Country.VIETNAM)
        if job.location:
            return Location(city=job.location)
        return None
