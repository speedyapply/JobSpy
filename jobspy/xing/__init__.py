from __future__ import annotations

import json
from datetime import date, datetime
from typing import Iterable

from bs4 import BeautifulSoup

from jobspy.model import (
    DescriptionFormat,
    JobPost,
    JobResponse,
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
)
from jobspy.xing.constant import headers, search_url

log = create_logger("Xing")


class Xing(Scraper):
    base_url = "https://www.xing.com"

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
        search_url_override: str | None = None,
        cookies: dict[str, str] | None = None,
    ):
        super().__init__(Site.XING, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)
        self.session = create_session(
            proxies=self.proxies,
            ca_cert=ca_cert,
            is_tls=False,
            has_retry=True,
        )
        self.session.headers.update(headers)
        if user_agent:
            self.session.headers["user-agent"] = user_agent
        if cookies:
            self.session.cookies.update(cookies)
        self.scraper_input = None
        self.search_url = search_url_override or search_url

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        params = self._build_params(scraper_input)
        response = self.session.get(
            self.search_url,
            params=params,
            timeout=getattr(scraper_input, "request_timeout", 60),
        )

        if "login.xing.com" in response.url:
            log.warning(
                "Xing redirects unauthenticated users to login; no public jobs were returned"
            )
            return JobResponse(jobs=[])

        soup = BeautifulSoup(response.text, "html.parser")
        jobs = list(self._extract_job_posts(soup))
        if not jobs:
            log.warning("Xing page did not expose any parseable job postings")

        return JobResponse(jobs=jobs[: scraper_input.results_wanted])

    def _build_params(self, scraper_input: ScraperInput) -> dict[str, str]:
        params: dict[str, str] = {}
        if scraper_input.search_term:
            params["keywords"] = scraper_input.search_term
        if scraper_input.location:
            params["location"] = scraper_input.location
        if scraper_input.is_remote:
            params["remote"] = "true"
        if scraper_input.hours_old:
            params["days"] = str(max(scraper_input.hours_old // 24, 1))
        if scraper_input.job_type:
            params["job_type"] = scraper_input.job_type.value[0]
        return params

    def _extract_job_posts(self, soup: BeautifulSoup) -> Iterable[JobPost]:
        for script_tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw_json = script_tag.string or script_tag.get_text(strip=True)
            if not raw_json:
                continue
            try:
                payload = json.loads(raw_json)
            except json.JSONDecodeError:
                continue

            job_postings = payload if isinstance(payload, list) else [payload]
            for entry in job_postings:
                if not isinstance(entry, dict):
                    continue
                if entry.get("@type") != "JobPosting":
                    continue

                job_post = self._parse_job_posting(entry)
                if job_post:
                    yield job_post

    def _parse_job_posting(self, job_data: dict) -> JobPost | None:
        job_url = job_data.get("url")
        title = job_data.get("title")
        company_name = (job_data.get("hiringOrganization") or {}).get("name")
        if not job_url or not title:
            return None

        location = self._parse_location(job_data.get("jobLocation"))
        date_posted = self._parse_date(job_data.get("datePosted"))
        description = job_data.get("description")
        if description and self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
            description = markdown_converter(description)

        return JobPost(
            id=f"xg-{abs(hash(job_url))}",
            title=title,
            company_name=company_name,
            job_url=job_url,
            location=location,
            description=description,
            date_posted=date_posted,
            emails=extract_emails_from_text(description) if description else None,
        )

    def _parse_location(self, job_location: object) -> Location | None:
        if not job_location:
            return None

        location_data = job_location[0] if isinstance(job_location, list) else job_location
        address = location_data.get("address") if isinstance(location_data, dict) else None
        if not isinstance(address, dict):
            return None

        return Location(
            city=address.get("addressLocality"),
            state=address.get("addressRegion"),
            country=address.get("addressCountry"),
        )

    def _parse_date(self, value: str | None) -> date | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None