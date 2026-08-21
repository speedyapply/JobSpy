from __future__ import annotations

import re
import logging
from datetime import datetime, timedelta, date

from bs4 import BeautifulSoup

from jobspy.model import (
    Scraper,
    ScraperInput,
    Site,
    JobPost,
    JobResponse,
    Location,
    Country,
    JobType,
    Compensation,
    CompensationInterval,
)
from jobspy.util import create_logger, create_session, extract_job_type

log = create_logger("Seek")


class SeekScraper(Scraper):
    base_url = "https://au.seek.com"
    delay = 1.5
    band_delay = 2.0

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(Site.SEEK, proxies=proxies, ca_cert=ca_cert)
        self.scraper_input = None
        self.session = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.session = create_session(
            proxies=self.proxies, ca_cert=self.ca_cert, is_tls=False, has_retry=True
        )

        # Warm up session with homepage to set cookies
        self.session.get(f"{self.base_url}/")

        job_list: list[JobPost] = []
        page = 1
        results_wanted = scraper_input.results_wanted or 15

        while len(job_list) < results_wanted:
            log.info(f"Fetching Seek jobs page {page}")
            job_elements = self._fetch_jobs(
                scraper_input.search_term, page
            )
            if not job_elements:
                log.info("No job elements found on page. Ending pagination.")
                break

            initial_count = len(job_list)
            for job_el in job_elements:
                try:
                    job_post = self._extract_job_info(job_el)
                    if job_post:
                        job_list.append(job_post)
                        if len(job_list) >= results_wanted:
                            break
                except Exception as e:
                    log.error(f"Seek: Error extracting job info: {e}")
                    continue

            if len(job_list) == initial_count:
                log.info(f"No new jobs found on page {page}. Ending pagination.")
                break

            page += 1

        job_list = job_list[:results_wanted]
        return JobResponse(jobs=job_list)

    def _fetch_jobs(self, query: str, page: int) -> list | None:
        """Fetch job search results for the given query and page."""
        try:
            search_path = self._search_term_to_path(query)
            url = f"{self.base_url}/{search_path}?page={page}"
            response = self.session.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # Each job card is an <article> inside the search results
            results_div = soup.find(
                "div", attrs={"data-automation": "searchResults"}
            )
            if not results_div:
                log.warning("Could not find searchResults div")
                return None

            job_articles = results_div.find_all("article")
            log.debug(f"Found {len(job_articles)} job <article> elements")
            return job_articles if job_articles else None
        except Exception as e:
            log.error(f"Seek: Error fetching jobs - {e}")
            return None

    def _extract_job_info(self, article: BeautifulSoup) -> JobPost | None:
        """Extract job info from a search-results <article> element."""
        title_el = article.find(attrs={"data-automation": "jobTitle"})
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        job_url_suffix = title_el.get("href", "")
        if not job_url_suffix:
            return None
        job_url = f"{self.base_url}{job_url_suffix}"

        # Extract job ID from URL
        job_id_match = re.search(r"/job/(\d+)", job_url_suffix)
        job_id = f"seek-{job_id_match.group(1)}" if job_id_match else None

        company_el = article.find(attrs={"data-automation": "jobCompany"})
        company_name = company_el.get_text(strip=True) if company_el else None

        location_el = article.find(attrs={"data-automation": "jobLocation"})
        location_raw = location_el.get_text(strip=True) if location_el else None

        salary_el = article.find(attrs={"data-automation": "jobSalary"})
        salary_raw = salary_el.get_text(strip=True) if salary_el else None

        date_el = article.find(attrs={"data-automation": "jobListingDate"})
        date_raw = date_el.get_text(strip=True) if date_el else None

        desc_el = article.find(attrs={"data-automation": "jobShortDescription"})
        description_short = (
            desc_el.get_text(strip=True) if desc_el else None
        )

        compensation = self._parse_salary(salary_raw)
        date_posted = self._parse_date(date_raw)

        location_obj = None
        if location_raw:
            location_obj = Location(
                city=location_raw.split(",")[0].strip(),
                state=None,
                country=Country.AUSTRALIA,
            )

        return JobPost(
            id=job_id,
            title=title,
            company_name=company_name,
            job_url=job_url,
            location=location_obj,
            compensation=compensation,
            date_posted=date_posted,
            description=description_short,
        )

    def _parse_salary(self, salary_raw: str | None) -> Compensation | None:
        """Parse a Seek salary string like '$170,000 – $190,000 + Super'."""
        if not salary_raw:
            return None

        # Patterns: $100,000 – $130,000, $100k - $130k, $40 - $50/hr
        salary_clean = salary_raw.replace(",", "").replace("$", "").strip()

        range_match = re.search(
            r"(\d+(?:\.\d+)?)\s*[–\-—]\s*(\d+(?:\.\d+)?)", salary_clean
        )
        if not range_match:
            return None

        min_amount = float(range_match.group(1))
        max_amount = float(range_match.group(2))

        interval = CompensationInterval.YEARLY
        if "/hr" in salary_raw.lower() or "/hour" in salary_raw.lower():
            interval = CompensationInterval.HOURLY
        elif "/day" in salary_raw.lower():
            interval = CompensationInterval.DAILY

        return Compensation(
            interval=interval,
            min_amount=min_amount,
            max_amount=max_amount,
            currency="AUD",
        )

    def _parse_date(self, date_raw: str | None) -> date | None:
        """Parse relative dates like '13h ago', '7d ago', '30d+ ago', 'Featured'."""
        if not date_raw:
            return None

        today = datetime.now().date()
        date_lower = date_raw.lower().strip()

        # Skip non-date text
        if date_lower in ("featured", "promoted", "new"):
            return today

        match = re.match(r"(\d+)([hd])\+?\s*ago", date_lower)
        if not match:
            return today

        value = int(match.group(1))
        unit = match.group(2)

        if unit == "h":
            return today
        elif unit == "d":
            return today - timedelta(days=value)

        return today

    def _search_term_to_path(self, query: str) -> str:
        """Convert a search term into a Seek URL path."""
        # Replace spaces with hyphens, lowercase, remove special chars
        path = re.sub(r"[^a-z0-9\s-]", "", query.lower().strip())
        path = re.sub(r"\s+", "-", path)
        return f"{path}-jobs"
