from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime
from urllib.parse import quote, urlencode, urljoin

from bs4 import BeautifulSoup

from jobspy.bayt.constant import (
    all_countries,
    country_aliases,
    date_intervals,
    job_type_codes,
    jobs_per_page,
    schema_job_types,
)
from jobspy.model import (
    Compensation,
    CompensationInterval,
    DescriptionFormat,
    Scraper,
    ScraperInput,
    Site,
    JobPost,
    JobResponse,
    Location,
    Country,
)
from jobspy.util import (
    create_logger,
    create_session,
    extract_emails_from_text,
    markdown_converter,
)

log = create_logger("Bayt")


def slugify(text: str) -> str:
    return quote("-".join(text.lower().split()), safe="")


class BaytScraper(Scraper):
    base_url = "https://www.bayt.com"
    delay = 2
    band_delay = 3

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(Site.BAYT, proxies=proxies, ca_cert=ca_cert)
        self.scraper_input = None
        self.session = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.session = create_session(proxies=self.proxies, ca_cert=self.ca_cert)
        country, city = self._location(scraper_input.location)
        job_list: list[JobPost] = []
        seen = set()
        first_page = page = scraper_input.offset // jobs_per_page + 1
        skip = scraper_input.offset % jobs_per_page

        while len(job_list) < scraper_input.results_wanted:
            if page > first_page:
                time.sleep(random.uniform(self.delay, self.delay + self.band_delay))
            log.info(f"search page: {page}")
            try:
                url = self._search_url(country, city, page)
                response = self.session.get(url, allow_redirects=True)
            except Exception as e:
                log.error(f"Bayt: {e}")
                break
            if response.status_code == 404 and (city or country != all_countries):
                wider = "the country" if city else "all countries"
                log.warning(
                    f"Bayt: location '{scraper_input.location}' not found, "
                    f"searching {wider}"
                )
                if city:
                    city = None
                else:
                    country = all_countries
                continue
            if response.status_code != 200:
                log.error(f"Bayt response status code {response.status_code}")
                break

            if page > 1 and f"page={page}" not in response.url:
                break
            cards = BeautifulSoup(response.text, "html.parser").select(
                "li[data-js-job]"
            )
            if page == first_page:
                cards = cards[skip:]

            cards = [card for card in cards if card.get("data-job-id") not in seen]
            if not cards:
                break
            seen.update(card.get("data-job-id") for card in cards)
            for job in cards:
                try:
                    job_post = self._process_job(job)
                except Exception as e:
                    log.warning(f"skipping job: {e}")
                    continue
                if job_post:
                    job_list.append(job_post)
                    if len(job_list) >= scraper_input.results_wanted:
                        break

            page += 1

        return JobResponse(jobs=job_list)

    @staticmethod
    def _location(location: str | None) -> tuple[str, str | None]:
        """ "Dubai, UAE" -> ("uae", "dubai"); a country alone -> (country, None)"""
        parts = [part.strip() for part in (location or "").split(",") if part.strip()]
        if not parts:
            return all_countries, None
        country = country_aliases.get(parts[-1].lower(), slugify(parts[-1]))
        city = slugify(parts[0]) if len(parts) > 1 else None
        return country, city

    def _search_url(self, country: str, city: str | None, page: int) -> str:
        slug = slugify(self.scraper_input.search_term or "")
        if not slug:
            path = ""  # all jobs
        elif city:
            path = f"{slug}-jobs-in-{city}/"
        else:
            path = f"{slug}-jobs/"

        filters = {}
        if hours_old := self.scraper_input.hours_old:
            interval = next(
                (v for hours, v in date_intervals if hours_old <= hours), None
            )
            if interval:
                filters["jb_last_modification_date_interval"] = interval
        if code := job_type_codes.get(self.scraper_input.job_type):
            filters["jb_employment_type"] = code
        if self.scraper_input.is_remote:
            filters["remote_working_type"] = 1
        params = {f"filters[{k}][]": v for k, v in filters.items()} | {"page": page}
        return f"{self.base_url}/en/{country}/jobs/{path}?{urlencode(params)}"

    def _process_job(self, job: BeautifulSoup) -> JobPost | None:
        link = job.select_one("h2 a[href]")
        if not link:
            return None
        job_url = urljoin(self.base_url, link["href"].strip())

        posted = job.select_one("[data-automation-jobactivedate]")
        stamp = posted.get("data-automation-jobactivedate", "") if posted else ""
        timestamp = int(stamp) if stamp.isdigit() else None
        hours_old = self.scraper_input.hours_old
        if hours_old and timestamp and timestamp < time.time() - hours_old * 3600:
            return None  # the date filter only narrows to 24 hours / 7 / 30 days
        if self.scraper_input.easy_apply and not job.select_one("div.jb-easy-apply a"):
            return None

        company = job.select_one("h2 + div.job-company-location-wrapper")
        company_link = company.select_one("a[href*='/company/']") if company else None
        logo = job.select_one("img.jb-logo")
        logo_url = (
            urljoin(self.base_url, logo["src"]) if logo and logo.get("src") else None
        )
        if logo_url and "/bayt/assets/" in logo_url:
            logo_url = None

        # e.g. "Qurtubah, Riyadh, Saudi Arabia" -> city=Riyadh, country=Saudi Arabia
        location_tag = job.select_one("dt.jb-label-location")
        parts = (
            [span.get_text(strip=True) for span in location_tag.find_all("span")]
            if location_tag
            else []
        )
        salary = job.select_one("dt.jb-label-salary")
        # "Management · 3-7 Years of Experience" -> management
        level_tag = job.select_one("dt.jb-label-careerlevel")
        level = level_tag.get_text(" ", strip=True).split("·")[0] if level_tag else ""
        level = level.strip().lower()

        description, job_type = None, None
        if self.scraper_input.fetch_description:
            description, job_type = self._fetch_details(job_url)

        return JobPost(
            id=f"bayt-{job['data-job-id']}",
            title=link.get_text(strip=True),
            company_name=(company.get_text(strip=True) or None) if company else None,
            company_url=(
                urljoin(self.base_url, company_link["href"]) if company_link else None
            ),
            company_logo=logo_url,
            location=Location(
                city=parts[-2] if len(parts) > 1 else None,
                country=parts[-1] if parts else Country.WORLDWIDE,
            ),
            job_url=job_url,
            date_posted=datetime.fromtimestamp(timestamp).date() if timestamp else None,
            is_remote=job.select_one("dt.jb-label-remote") is not None,
            job_level=level if level and "experience" not in level else None,
            compensation=(
                self._parse_salary(salary.get_text(" ", strip=True)) if salary else None
            ),
            description=description,
            emails=extract_emails_from_text(description),
            job_type=job_type,
        )

    @staticmethod
    def _parse_salary(text: str) -> Compensation | None:
        """ "AED 29,380 - AED 33,053" / "$3,000 - $4,000"; monthly, as job pages say"""
        match = re.fullmatch(
            r"([A-Z]{3}|\$) ?([\d,]+(?:\.\d+)?) - (?:[A-Z]{3}|\$)? ?([\d,]+(?:\.\d+)?)",
            text,
        )
        if not match:
            return None
        currency, low, high = match.groups()
        return Compensation(
            interval=CompensationInterval.MONTHLY,
            min_amount=float(low.replace(",", "")),
            max_amount=float(high.replace(",", "")),
            currency="USD" if currency == "$" else currency,
        )

    def _fetch_details(self, job_url: str) -> tuple[str | None, list | None]:
        """Description and job type from the job page's schema.org JobPosting."""
        try:
            response = self.session.get(job_url)
            script = BeautifulSoup(response.text, "html.parser").select_one(
                'script[type="application/ld+json"]'
            )
            posting = json.loads(script.string)
            if posting["@type"] != "JobPosting":
                return None, None
            job_type = schema_job_types.get(posting.get("employmentType"))
        except Exception:
            return None, None

        description = posting.get("description")
        if (
            description
            and self.scraper_input.description_format == DescriptionFormat.MARKDOWN
        ):
            description = markdown_converter(description)
        return description, [job_type] if job_type else None
