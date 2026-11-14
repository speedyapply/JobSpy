from __future__ import annotations

import random
import re
import time
from typing import Any

from bs4 import BeautifulSoup, Tag

from jobspy.exception import JobStreetException
from jobspy.jobstreet.constant import headers as jobstreet_headers
from jobspy.jobstreet.util import parse_date_posted, parse_location
from jobspy.model import (
    CompensationInterval,
    JobPost,
    Location,
    Scraper,
    ScraperInput,
)
from jobspy.util import TLSRotating, create_session, description_fields


class JobStreet(Scraper):
    """JobStreet Indonesia scraper. Extracts job data from search result pages only."""

    base_url = "https://id.jobstreet.com/id"
    jobs_per_page = 20
    delay = 3
    band_delay = 2
    max_pages = 20
    retry_attempts = 3
    retry_delay = 5

    def scrape(self, scraper_input: ScraperInput) -> list[JobPost]:
        """Scrape JobStreet Indonesia search results."""
        self.scraper_input = scraper_input

        # TLS client mimics a real browser fingerprint; rotating proxies avoid blocks.
        self.session = create_session(
            TLSRotating(scraper_input.proxies),
            scraper_input,
            jobstreet_headers,
        )

        job_list: list[JobPost] = []
        seen_ids: set[str] = set()
        page = 1
        wanted = scraper_input.results_wanted + scraper_input.offset

        while len(job_list) < wanted and page <= self.max_pages:
            self.log.info(f"Fetching JobStreet page {page} / {self.max_pages}")
            try:
                jobs_on_page = self._fetch_page(page)
                if not jobs_on_page:
                    self.log.info(f"No jobs found on page {page}. Stopping.")
                    break

                initial_count = len(job_list)
                for job in jobs_on_page:
                    if job.id and job.id in seen_ids:
                        continue
                    if job.id:
                        seen_ids.add(job.id)
                    job_list.append(job)
                    if len(job_list) >= wanted:
                        break

                if len(job_list) == initial_count:
                    self.log.info(f"No new jobs on page {page}. Stopping.")
                    break

            except Exception as e:
                self.log.error(f"Error fetching page {page}: {e}")
                break

            page += 1
            if len(job_list) < wanted:
                sleep_time = random.uniform(self.delay, self.delay + self.band_delay)
                self.log.debug(f"Sleeping for {sleep_time:.2f}s")
                time.sleep(sleep_time)

        return job_list[
            scraper_input.offset : scraper_input.offset + scraper_input.results_wanted
        ]

    def _build_url(self) -> str:
        """Build JobStreet search URL using slug format."""
        search_term = self.scraper_input.search_term or ""
        location = self.scraper_input.location or "Indonesia"

        # Map common locations to JobStreet's preferred slug format.
        location_map = {
            "tangerang": "Tangerang-Banten",
            "tangerang banten": "Tangerang-Banten",
        }

        location_key = location.strip().lower()
        location_slug = location_map.get(location_key, location)
        location_slug = "-".join(location_slug.split())

        search_slug = (
            "-".join(search_term.lower().split()) + "-jobs" if search_term else "jobs"
        )

        return f"{self.base_url}/{search_slug}/in-{location_slug}"

    def _fetch_page(self, page: int) -> list[JobPost]:
        """Fetch and parse one search result page."""
        url = self._build_url()
        params: dict[str, int] = {}
        if page > 1:
            params["page"] = page

        # Map hours_old to JobStreet daterange filter.
        if self.scraper_input.hours_old:
            hours = self.scraper_input.hours_old
            if hours <= 24:
                params["daterange"] = 1
            elif hours <= 72:
                params["daterange"] = 3
            elif hours <= 168:
                params["daterange"] = 7
            elif hours <= 336:
                params["daterange"] = 14
            else:
                params["daterange"] = 30
            self.log.debug(f"Using daterange={params['daterange']} for hours_old={hours}")

        response = self._request(url, params)
        text = getattr(response, "text", "")
        return self._parse_cards(str(text))

    def _request(self, url: str, params: dict[str, int]) -> object:
        """GET with cookie clearing and retries, to survive anti-bot responses."""
        last_error: JobStreetException | None = None
        response: Any | None = None

        for attempt in range(1, self.retry_attempts + 1):
            # Fresh cookies per request; matches the original clear_cookies=True.
            self.session.cookies.clear()
            response = self.session.get(url, params=params, allow_redirects=True)
            status = getattr(response, "status_code", 0)
            if status in range(200, 400):
                return response

            text = getattr(response, "text", "") or ""
            last_error = JobStreetException(f"HTTP {status}: {str(text)[:200]}")
            if attempt < self.retry_attempts:
                self.log.warning(
                    f"{last_error} (attempt {attempt}/{self.retry_attempts})"
                )
                time.sleep(self.retry_delay)

        raise last_error or JobStreetException(f"JobStreet request failed: {url}")

    def _parse_cards(self, html: str) -> list[JobPost]:
        """Parse the job cards on one search result page and apply location filter."""
        soup = BeautifulSoup(html, "html.parser")
        job_cards = soup.find_all("article")
        self.log.debug(f"Found {len(job_cards)} job cards")

        jobs: list[JobPost] = []
        requested_location = (
            self.scraper_input.location or "Indonesia"
        ).strip().lower()

        # Expand "Tangerang" to cover the whole Tangerang metropolitan area.
        location_matchers = {
            "tangerang": {
                "tangerang",
                "serpong",
                "bsd",
                "alam sutera",
                "cipondoh",
                "ciledug",
                "batuceper",
                "benda",
                "jatiuwung",
                "karawaci",
                "larangan",
                "periuk",
                "pinang",
                "tangerang selatan",
                "kabupaten tangerang",
                "kota tangerang",
                "banten",
            }
        }
        accepted_matchers = location_matchers.get(
            requested_location, {requested_location}
        )

        for card in job_cards:
            try:
                job = self._parse_card(card)
                if not job:
                    continue

                # Filter out jobs that don't match the requested location.
                if requested_location != "indonesia":
                    job_location = " ".join(
                        getattr(job.location, field, "") or ""
                        for field in ("city", "state", "country")
                    ).lower()
                    if not any(
                        matcher in job_location for matcher in accepted_matchers
                    ):
                        self.log.debug(
                            f"Skipping job '{job.title}' in '{job_location}' "
                            f"(requested {requested_location})"
                        )
                        continue
                jobs.append(job)
            except Exception as e:
                self.log.warning(f"Failed to parse job card: {e}")
                continue

        return jobs

    def _parse_card(self, card: Tag) -> JobPost | None:
        """Parse a single job card into JobPost."""
        link_el = (
            card.select_one('[data-automation="job-list-view-job-link"]')
            or card.select_one('[data-automation="job-list-item-link-overlay"]')
            or card.find("a")
        )
        if not link_el:
            return None

        href = link_el.get("href", "")
        job_url = str(href) if isinstance(href, str) else ""
        if not job_url.startswith("http"):
            job_url = f"https://id.jobstreet.com{job_url}"

        job_id = job_url.split("/")[-1] if "/job/" in job_url else None

        title_el = card.select_one('[data-automation="jobTitle"]')
        title = title_el.get_text(strip=True) if title_el else None

        company_el = card.select_one('[data-automation="jobCompany"]')
        company = company_el.get_text(strip=True) if company_el else None

        location_el = card.select_one('[data-automation="jobLocation"]')
        location = (
            parse_location(location_el.get_text(strip=True))
            if location_el
            else Location(country="Indonesia")
        )

        desc_el = card.select_one('[data-automation="jobShortDescription"]')
        description_kwargs: dict[str, Any] = {}
        if desc_el:
            description_kwargs = description_fields(
                str(desc_el), self.scraper_input.description_format
            )

        salary_el = card.select_one('[data-automation="jobSalary"]')
        salary_kwargs: dict[str, Any] = {}
        if salary_el:
            salary_kwargs = self._extract_salary(salary_el.get_text(strip=True))

        date_el = card.select_one('[data-automation="jobListingDate"]')
        date_posted = (
            parse_date_posted(date_el.get_text(strip=True)) if date_el else None
        )

        if not title or not job_url:
            return None

        return JobPost(
            id=job_id,
            title=title,
            company=company,
            job_url=job_url,
            location=location,
            date_posted=date_posted,
            **description_kwargs,
            **salary_kwargs,
        )

    @staticmethod
    def _extract_salary(text: str) -> dict[str, Any]:
        """Extract salary fields from Indonesian formatted text."""
        if not text:
            return {}

        interval_map = {
            "hour": CompensationInterval.HOURLY,
            "hourly": CompensationInterval.HOURLY,
            "jam": CompensationInterval.HOURLY,
            "day": CompensationInterval.DAILY,
            "daily": CompensationInterval.DAILY,
            "hari": CompensationInterval.DAILY,
            "week": CompensationInterval.WEEKLY,
            "weekly": CompensationInterval.WEEKLY,
            "minggu": CompensationInterval.WEEKLY,
            "month": CompensationInterval.MONTHLY,
            "monthly": CompensationInterval.MONTHLY,
            "bulan": CompensationInterval.MONTHLY,
            "year": CompensationInterval.YEARLY,
            "yearly": CompensationInterval.YEARLY,
            "tahun": CompensationInterval.YEARLY,
        }

        # Match patterns like "Rp 10.000.000 – Rp 15.000.000 per month".
        match = re.search(
            r"Rp\s*([\d.]+)\s*(?:–|-)\s*Rp\s*([\d.]+)\s*(?:per\s*(\w+))?",
            text,
            re.IGNORECASE,
        )
        if match:
            min_str = match.group(1).replace(".", "")
            max_str = match.group(2).replace(".", "")
            interval_str = (match.group(3) or "month").lower()
            return {
                "interval": interval_map.get(
                    interval_str, CompensationInterval.MONTHLY
                ),
                "min_amount": float(min_str) if min_str else None,
                "max_amount": float(max_str) if max_str else None,
                "currency": "IDR",
                "salary_source": "direct_data",
            }

        # Single amount: "Rp 10.000.000 per month".
        match = re.search(
            r"Rp\s*([\d.]+)\s*(?:per\s*(\w+))?", text, re.IGNORECASE
        )
        if match:
            amount_str = match.group(1).replace(".", "")
            interval_str = (match.group(2) or "month").lower()
            return {
                "interval": interval_map.get(
                    interval_str, CompensationInterval.MONTHLY
                ),
                "min_amount": float(amount_str) if amount_str else None,
                "max_amount": None,
                "currency": "IDR",
                "salary_source": "direct_data",
            }

        return {}
