from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta
from typing import Any

from jobspy.google.constant import async_param, headers_initial, headers_jobs
from jobspy.google.util import find_job_info, find_job_info_initial_page
from jobspy.model import (
    JobPost,
    JobType,
    Location,
    Scraper,
    ScraperInput,
)
from jobspy.util import RequestsRotating, create_session, extract_emails_from_text


class Google(Scraper):
    def __init__(self) -> None:
        super().__init__()
        self.country = None
        self.jobs_per_page = 10
        self.seen_urls: set[str | None] = set()
        self.url = "https://www.google.com/search"
        self.jobs_url = "https://www.google.com/async/callback:550"

    def scrape(self, scraper_input: ScraperInput) -> list[JobPost]:
        """
        Scrapes Google for jobs with scraper_input criteria.
        :param scraper_input: Information about job search criteria.
        :return: a list of jobs.
        """
        self.scraper_input = scraper_input
        self.scraper_input.results_wanted = min(900, scraper_input.results_wanted)

        self.session = create_session(
            RequestsRotating(scraper_input.proxies), scraper_input
        )
        try:
            forward_cursor, job_list = self._get_initial_cursor_and_jobs()
        except Exception as e:
            self.fail(str(e))
            return []
        if forward_cursor is None:
            return job_list

        page = 1

        while (
            len(self.seen_urls) < scraper_input.results_wanted + scraper_input.offset
            and forward_cursor
        ):
            self.log.info(
                f"search page: {page} / {math.ceil(scraper_input.results_wanted / self.jobs_per_page)}"
            )
            try:
                jobs, forward_cursor = self._get_jobs_next_page(forward_cursor)
            except Exception as e:
                self.fail(str(e))
                break
            if not jobs:
                self.log.info(f"found no jobs on page: {page}")
                break
            job_list += jobs
            page += 1
        return job_list[
            scraper_input.offset : scraper_input.offset + scraper_input.results_wanted
        ]

    def _get_initial_cursor_and_jobs(self) -> tuple[str | None, list[JobPost]]:
        """Gets initial cursor and jobs to paginate through job listings"""
        query = f"{self.scraper_input.search_term} jobs"

        def get_time_range(hours_old: int) -> str:
            if hours_old <= 24:
                return "since yesterday"
            elif hours_old <= 72:
                return "in the last 3 days"
            elif hours_old <= 168:
                return "in the last week"
            else:
                return "in the last month"

        job_type_mapping = {
            JobType.FULL_TIME: "Full time",
            JobType.PART_TIME: "Part time",
            JobType.INTERNSHIP: "Internship",
            JobType.CONTRACT: "Contract",
        }

        if self.scraper_input.job_type in job_type_mapping:
            query += f" {job_type_mapping[self.scraper_input.job_type]}"

        if self.scraper_input.location:
            query += f" near {self.scraper_input.location}"

        if self.scraper_input.hours_old:
            time_filter = get_time_range(self.scraper_input.hours_old)
            query += f" {time_filter}"

        if self.scraper_input.is_remote:
            query += " remote"

        if self.scraper_input.google_search_term:
            query = self.scraper_input.google_search_term

        params = {"q": query, "udm": "8"}
        response = self.session.get(self.url, headers=headers_initial, params=params)
        if response.status_code != 200:
            self.fail(f"response status code {response.status_code}")
            return None, []

        pattern_fc = r'<div jsname="Yust4d"[^>]+data-async-fc="([^"]+)"'
        match_fc = re.search(pattern_fc, response.text)
        data_async_fc = match_fc.group(1) if match_fc else None
        jobs_raw = find_job_info_initial_page(response.text, self.log)
        jobs = []
        for job_raw in jobs_raw:
            try:
                job_post = self._parse_job(job_raw)
            except Exception as e:
                self.log.warning(f"skipping job: {e}")
                continue
            if job_post:
                jobs.append(job_post)
        if not jobs and not data_async_fc:
            self.fail("no job data returned")
        return data_async_fc, jobs

    def _get_jobs_next_page(
        self, forward_cursor: str
    ) -> tuple[list[JobPost], str | None]:
        params = {"fc": [forward_cursor], "fcv": ["3"], "async": [async_param]}
        response = self.session.get(self.jobs_url, headers=headers_jobs, params=params)
        if response.status_code != 200:
            self.fail(f"response status code {response.status_code}")
            return [], None
        return self._parse_jobs(response.text)

    def _parse_jobs(self, job_data: str) -> tuple[list[JobPost], str | None]:
        """
        Parses jobs on a page with next page cursor
        """
        start_idx = job_data.find("[[[")
        end_idx = job_data.rindex("]]]") + 3
        s = job_data[start_idx:end_idx]
        parsed = json.loads(s)[0]

        pattern_fc = r'data-async-fc="([^"]+)"'
        match_fc = re.search(pattern_fc, job_data)
        data_async_fc = match_fc.group(1) if match_fc else None
        jobs_on_page = []
        for array in parsed:
            _, job_data = array
            if not job_data.startswith("[[["):
                continue
            job_d = json.loads(job_data)

            job_info = find_job_info(job_d)
            try:
                if job_info is None:
                    raise ValueError("no job info")
                job_post = self._parse_job(job_info)
            except Exception as e:
                self.log.warning(f"skipping job: {e}")
                continue
            if job_post:
                jobs_on_page.append(job_post)
        return jobs_on_page, data_async_fc

    def _parse_job(self, job_info: list[Any]) -> JobPost | None:
        job_url = job_info[3][0][0] if job_info[3] and job_info[3][0] else None
        if job_url in self.seen_urls:
            return None
        self.seen_urls.add(job_url)
        if job_url is None:
            raise ValueError("no job url")

        title = job_info[0]
        company_name = job_info[1]
        location = city = job_info[2]
        state = country = date_posted = None
        if location and "," in location:
            city, state, *country = [*map(lambda x: x.strip(), location.split(","))]

        days_ago_str = job_info[12]
        if isinstance(days_ago_str, str):
            match = re.search(r"\d+", days_ago_str)
            if match:
                days_ago = int(match.group())
                date_posted = (datetime.now() - timedelta(days=days_ago)).date()

        description = job_info[19]
        # the title and location, as LinkedIn: a description says "not remote" too
        text = f"{title} {location or ''}".lower()

        job_post = JobPost(
            id=f"go-{job_info[28]}",
            title=title,
            company=company_name,
            location=Location(
                city=city, state=state, country=country[0] if country else None
            ),
            job_url=job_url,
            date_posted=date_posted,
            is_remote=any(word in text for word in ("remote", "work from home", "wfh")),
            description=description,
            emails=extract_emails_from_text(description),
        )
        return job_post
