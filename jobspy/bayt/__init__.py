from __future__ import annotations

import json
import random
import re
import time
from itertools import takewhile
from urllib.parse import quote, urlencode, urljoin

from bs4 import BeautifulSoup

from jobspy.bayt.constant import (
    all_countries,
    country_aliases,
    date_intervals,
    job_type_codes,
    job_type_labels,
    jobs_per_page,
)
from jobspy.model import (
    Compensation,
    CompensationInterval,
    Scraper,
    ScraperInput,
    JobPost,
    JobResponse,
    Location,
    Country,
)
from jobspy.util import (
    create_logger,
    create_session,
    format_description,
    utc_date,
)

log = create_logger("Bayt")


def slugify(text: str) -> str:
    return quote("-".join(text.lower().split()), safe="")


class Bayt(Scraper):
    base_url = "https://www.bayt.com"
    delay = 2
    band_delay = 3

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.session = create_session(
            proxies=self.proxies, ca_cert=self.ca_cert, user_agent=self.user_agent
        )
        self.hybrid_ids = None
        job_type = scraper_input.job_type
        if job_type and job_type not in job_type_codes:
            log.warning(
                f"Bayt: job_type {job_type.value[0]} isn't supported, ignoring it"
            )
        self.country, self.city = self._location(scraper_input.location)
        hours_old = scraper_input.hours_old
        oldest = time.time() - hours_old * 3600 if hours_old else 0
        job_list: list[JobPost] = []
        seen = set()
        first_page = page = scraper_input.offset // jobs_per_page + 1
        skip = scraper_input.offset % jobs_per_page

        while len(job_list) < scraper_input.results_wanted:
            if page > first_page:
                time.sleep(random.uniform(self.delay, self.delay + self.band_delay))
            log.info(f"search page: {page}")
            cards = self._fetch_cards(page)
            if cards is None:
                break
            if page == first_page:
                cards = cards[skip:]

            cards = [card for card in cards if card.get("data-job-id") not in seen]
            if not cards:
                break
            seen.update(card.get("data-job-id") for card in cards)
            new = list(
                takewhile(lambda c: (self._timestamp(c) or oldest) >= oldest, cards)
            )
            if new and scraper_input.is_remote and self.hybrid_ids is None:
                self.hybrid_ids = self._fetch_hybrid_ids()
                if self.hybrid_ids is None:
                    break
            for job in new:
                try:
                    job_post = self._process_job(job)
                except Exception as e:
                    log.warning(f"skipping job: {e}")
                    continue
                if job_post:
                    job_list.append(job_post)
                    if len(job_list) >= scraper_input.results_wanted:
                        break

            if len(new) < len(cards):
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

    def _search_url(self, page: int, hybrid: bool) -> str:
        slug = slugify(self.scraper_input.search_term or "")
        term = f"{slug}-" if slug else ""
        if self.city:
            path = f"{term}jobs-in-{self.city}/"
        else:
            path = f"{term}jobs/" if slug else ""  # all jobs

        params = {}
        hours_old = self.scraper_input.hours_old or 0
        interval = next((v for hours, v in date_intervals if 0 < hours_old <= hours), 0)
        if interval:
            params["filters[jb_last_modification_date_interval][]"] = interval
        if code := job_type_codes.get(self.scraper_input.job_type):
            params["filters[jb_employment_type][]"] = code
        if self.scraper_input.is_remote:
            params["filters[remote_working_type][]"] = 2 if hybrid else 1
        if hours_old:
            params["options[sort][]"] = "d"
        if self.scraper_input.easy_apply:
            params["options[jb_is_external_job][]"] = 1
        params["page"] = page
        return f"{self.base_url}/en/{self.country}/jobs/{path}?{urlencode(params)}"

    def _fetch_cards(self, page: int, hybrid: bool = False) -> list | None:
        """A search page's job cards: none past the last page, None when the request
        fails. A location the site doesn't have (404) is widened and asked again."""
        try:
            url = self._search_url(page, hybrid)
            response = self.session.get(url, allow_redirects=True)
        except Exception as e:
            log.error(f"Bayt: {e}")
            return None
        if response.status_code == 404 and (self.city or self.country != all_countries):
            wider = "the country" if self.city else "all countries"
            log.warning(
                f"Bayt: location '{self.scraper_input.location}' not found, "
                f"searching {wider}"
            )
            if self.city:
                self.city = None
            else:
                self.country = all_countries
            return self._fetch_cards(page, hybrid)
        if response.status_code != 200:
            log.error(f"Bayt response status code {response.status_code}")
            return None
        if page > 1 and f"page={page}" not in response.url:
            return []
        return BeautifulSoup(response.text, "html.parser").select("li[data-js-job]")

    def _fetch_hybrid_ids(self) -> set[str] | None:
        """The search's hybrid jobs: the remote filter returns them too, and not
        every card carries the label that tells them apart."""
        ids = set()
        page = 1
        while True:
            cards = self._fetch_cards(page, hybrid=True)
            if cards is None:
                return None
            new = {card.get("data-job-id") for card in cards} - ids
            ids |= new
            if len(cards) < jobs_per_page or not new:
                return ids
            page += 1
            time.sleep(random.uniform(self.delay, self.delay + self.band_delay))

    @staticmethod
    def _timestamp(job: BeautifulSoup) -> int | None:
        posted = job.select_one("[data-automation-jobactivedate]")
        stamp = posted.get("data-automation-jobactivedate", "") if posted else ""
        return int(stamp) if stamp.isdigit() else None

    def _process_job(self, job: BeautifulSoup) -> JobPost | None:
        link = job.select_one("h2 a[href]")
        job_id = job["data-job-id"]
        job_url = urljoin(self.base_url, link["href"])
        if self.scraper_input.easy_apply and not job.select_one("div.jb-easy-apply a"):
            return None
        remote_tag = job.select_one("dt.jb-label-remote")
        is_remote = bool(remote_tag) and remote_tag.get_text(strip=True) == "Remote"
        if self.scraper_input.is_remote:
            if job_id in self.hybrid_ids:
                return None
            is_remote = True

        company = job.select_one("h2 + div.job-company-location-wrapper")
        company_link = company.select_one("a[href*='/company/']") if company else None
        logo = job.select_one("img.jb-logo")
        logo_url = (
            urljoin(self.base_url, logo["src"]) if logo and logo.get("src") else None
        )
        if logo_url and "/bayt/assets/" in logo_url:
            logo_url = None

        location_tag = job.select_one("dt.jb-label-location")
        parts = (
            [span.get_text(strip=True) for span in location_tag.find_all("span")]
            if location_tag
            else []
        )
        has_state = len(parts) == 3 and parts[-1] == "USA"
        salary = job.select_one("dt.jb-label-salary")
        level_tag = job.select_one("dt.jb-label-careerlevel")
        level = level_tag.get_text(" ", strip=True).split("·") if level_tag else []
        level = [part.strip() for part in level]

        job_post = JobPost(
            id=f"bayt-{job_id}",
            title=link.get_text(strip=True),
            company_name=(company.get_text(strip=True) or None) if company else None,
            company_url=(
                urljoin(self.base_url, company_link["href"]) if company_link else None
            ),
            company_logo=logo_url,
            location=Location(
                city=parts[0 if has_state else -2] if len(parts) > 1 else None,
                state=parts[1] if has_state else None,
                country=parts[-1] if parts else Country.WORLDWIDE,
            ),
            job_url=job_url,
            date_posted=utc_date(self._timestamp(job)),
            is_remote=is_remote,
            job_level=next(
                (part.lower() for part in level if "Experience" not in part), None
            ),
            experience_range=next(
                (
                    part.removesuffix(" of Experience")
                    for part in level
                    if "Experience" in part
                ),
                None,
            ),
            compensation=(
                self._parse_salary(salary.get_text(" ", strip=True)) if salary else None
            ),
        )
        if self.scraper_input.fetch_description:
            details = self._fetch_details(job_id, job_url)
            details["is_remote"] = is_remote or details.get("is_remote", False)
            job_post = job_post.model_copy(update=details)
        return job_post

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

    def _fetch_details(self, job_id: str, job_url: str) -> dict:
        """The description from the job page's schema.org JobPosting, the rest from
        the rows at the top of the page: the JobPosting says FULL_TIME for a job
        with no type or one it has no value for, TELECOMMUTE for hybrid jobs too,
        and 1 opening when the page states none."""
        try:
            response = self.session.get(job_url, allow_redirects=True)
            if response.status_code != 200:
                log.warning(
                    f"Bayt response status code {response.status_code} for job {job_id}"
                )
                return {}
            soup = BeautifulSoup(response.text, "html.parser")
            posting = json.loads(
                soup.select_one('script[type="application/ld+json"]').string
            )
            if posting["@type"] != "JobPosting":
                raise ValueError("no JobPosting")
        except Exception as e:
            log.warning(f"Bayt: job {job_id}: {e}")
            return {}

        def row(name: str) -> list[str]:
            tag = soup.select_one(f'[data-automation-id="id_{name}"]')
            return [part.strip() for part in tag.get_text().split("·")] if tag else []

        description, emails = format_description(
            posting.get("description"), self.scraper_input.description_format
        )
        job_type = job_type_labels.get(next(iter(row("type_level_experience")), None))
        company = row("company_employees_industry")
        openings = re.match(r"\d+", "".join(row("number_of_vacancies")))
        return {
            "description": description or None,
            "emails": emails,
            "job_type": [job_type] if job_type else None,
            "is_remote": row("remote_working") == ["Remote"],
            "vacancy_count": int(openings[0]) if openings else None,
            "company_num_employees": next(
                (part for part in company if "Employees" in part), None
            ),
            "company_industry": next(
                (part for part in company if "Employees" not in part), None
            ),
        }
