from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from jobspy.hellowork.constant import (
    date_windows,
    description_headings,
    job_type_labels,
    job_type_params,
    jobs_per_page,
    km_per_mile,
    paris_time,
    pay_intervals,
    related_list,
)
from jobspy.model import (
    Compensation,
    Country,
    JobPost,
    JobResponse,
    Location,
    Scraper,
    ScraperInput,
)
from jobspy.util import (
    create_logger,
    create_session,
    format_description,
    utc_date,
)

log = create_logger("HelloWork")


class HelloWork(Scraper):
    base_url = "https://www.hellowork.com"
    search_url = f"{base_url}/fr-fr/emploi/recherche.html"
    delay = 2
    band_delay = 3

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
                    self.search_url, params=params | {"p": page}
                )
                if response.status_code != 200:
                    log.error(f"HelloWork response status code {response.status_code}")
                    break
                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.select("li[data-id-storage-target=item]")
                pager = soup.select_one("input[type=number][max]")
                last_page = int(pager["max"]) if pager else page
            except Exception as e:
                log.error(f"HelloWork: {e}")
                break

            new_cards = [
                card
                for card in cards
                if card.get("data-id-storage-item-id") not in seen
            ]
            seen.update(card.get("data-id-storage-item-id") for card in cards)
            for card in new_cards[skip if page == first_page else 0 :]:
                try:
                    job_post = self._process_job(card)
                except Exception as e:
                    log.warning(f"skipping job: {e}")
                    continue
                if job_post:
                    job_list.append(job_post)
                    if len(job_list) >= scraper_input.results_wanted:
                        break

            if not new_cards or page >= last_page:
                break
            page += 1

        return JobResponse(jobs=job_list)

    def _search_params(self) -> dict:
        scraper_input = self.scraper_input
        params = {"k": scraper_input.search_term, "l": scraper_input.location}
        if scraper_input.location and scraper_input.distance is not None:
            params["ray"] = round(scraper_input.distance * km_per_mile)
        if hours_old := scraper_input.hours_old:
            params["d"] = next(
                (d for hours, d in date_windows if hours_old <= hours), None
            )
        job_type = scraper_input.job_type
        if job_type in job_type_params:
            params |= job_type_params[job_type]
        elif job_type:
            log.warning(
                f"HelloWork: job_type {job_type.value[0]} isn't supported, ignoring it"
            )
        if scraper_input.is_remote:
            params["t"] = "Complet"
        if scraper_input.easy_apply:
            log.warning("HelloWork: easy_apply isn't supported, ignoring it")
        return {
            name: value for name, value in params.items() if value not in (None, "")
        }

    @staticmethod
    def _hours_old(age: str) -> int | None:
        """ "il y a 3 heures" -> 3, "il y a 2 jours" -> 48; None when the card gives no age"""
        if age == "moins d'une heure":
            return 0
        match = re.fullmatch(r"il y a (\d+) (heure|jour)s?", age)
        if not match:
            return None
        return int(match[1]) * (24 if match[2] == "jour" else 1)

    def _process_job(self, card) -> JobPost | None:
        analytics = card.select_one("div[data-cy=serpCard]")
        if related_list in analytics["data-analytics-values-param"]:
            return None
        hours = self._hours_old(card.find_all("div")[-1].get_text(strip=True))
        hours_old = self.scraper_input.hours_old
        if hours_old and (hours or 0) >= hours_old:
            return None

        job_id = card["data-id-storage-item-id"]
        link = card.select_one("a[data-cy=offerTitle]")
        label = link["aria-label"]
        title, *company = (p.get_text(strip=True) for p in link.select("h3 p"))
        contract = card.select_one("div[data-cy=contractCard]")
        names = [contract.get_text(strip=True)] + re.findall(r"temps \w+", label)
        job_types = [job_type_labels[name] for name in names if name in job_type_labels]
        salary = next(
            (
                compensation
                for tag in contract.parent.find_all("div")
                if (compensation := self._parse_salary(tag.get_text(strip=True)))
            ),
            None,
        )
        logo = card.select_one('img[src*="/img/entreprises/"]')

        job_post = JobPost(
            id=f"hw-{job_id}",
            title=title,
            company_name="".join(company) or None,
            location=self._parse_location(
                card.select_one("div[data-cy=localisationCard]").get_text(strip=True)
            ),
            job_url=f"{self.base_url}{link['href']}",
            date_posted=(
                utc_date(time.time() - hours * 3600) if hours is not None else None
            ),
            job_type=job_types,
            is_remote="Télétravail complet" in label,
            compensation=salary,
            company_logo=logo["src"] if logo else None,
        )
        if self.scraper_input.fetch_description:
            details = self._fetch_details(job_id, job_post.job_url)
            job_post = job_post.model_copy(update=details)
        return job_post

    @staticmethod
    def _parse_location(text: str) -> Location:
        """ "Lyon 3e - 69" is a city and its department; anything else is kept as the site writes it"""
        city, _, department = text.rpartition(" - ")
        if re.fullmatch(r"\d{2,3}|2[AB]", department):
            return Location(city=city, state=department, country=Country.FRANCE)
        return Location(city=text)

    @staticmethod
    def _parse_salary(text: str) -> Compensation | None:
        """ "45 000 - 60 000 € / an", "12,31 € / heure", "66 000 - 85 000 USD / an" """
        number = r"\d[\d\s]*?(?:,\d+)?"
        match = re.fullmatch(
            rf"({number})(?: - ({number}))? ?(€|[A-Z]{{3}}) / (an|mois|jour|heure)",
            text,
        )
        if not match:
            return None
        low, high, currency, interval = match.groups()
        low, high = (
            float(re.sub(r"\s", "", amount).replace(",", "."))
            for amount in (low, high or low)
        )
        return Compensation(
            interval=pay_intervals[interval],
            min_amount=low,
            max_amount=high,
            currency="EUR" if currency == "€" else currency,
        )

    def _fetch_details(self, job_id: str, job_url: str) -> dict:
        """The job page's schema.org JobPosting; its date is Paris time written as UTC,
        and its jobLocationType says TELECOMMUTE for hybrid jobs too."""
        try:
            response = self.session.get(job_url)
            if response.status_code != 200:
                log.warning(
                    f"HelloWork response status code {response.status_code} "
                    f"for job {job_id}"
                )
                return {}
            soup = BeautifulSoup(response.text, "html.parser")
            posting = next(
                (
                    data
                    for script in soup.select('script[type="application/ld+json"]')
                    if (data := json.loads(script.string)).get("@type") == "JobPosting"
                ),
                {},
            )
            html = posting.get("description")
            if not html:
                section = next(
                    (
                        heading.find_parent("section")
                        for heading in soup.find_all("h2")
                        if heading.get_text(strip=True) in description_headings
                    ),
                    None,
                )
                if section:
                    for button in section.find_all("button"):
                        button.decompose()
                html = str(section) if section else None
            description, emails = format_description(
                html, self.scraper_input.description_format
            )
            details = {"description": description, "emails": emails}
            if posted := posting.get("datePosted"):
                posted = datetime.fromisoformat(posted.rstrip("Z"))
                posted = posted.replace(tzinfo=ZoneInfo(paris_time))
                posted = posted.astimezone(timezone.utc)
                details["date_posted"] = posted.date()
            experience = next(
                (
                    text.removeprefix("Exp. ")
                    for item in soup.find_all("li")
                    if (text := item.get_text(" ", strip=True)).startswith("Exp. ")
                ),
                None,
            )
            company = posting.get("hiringOrganization") or {}
            industry = posting.get("industry")
            skills = posting.get("skills")
            return details | {
                "company_url": company.get("sameAs"),
                "company_industry": (
                    ", ".join(industry) if isinstance(industry, list) else industry
                ),
                "job_function": posting.get("occupationalCategory"),
                "skills": [skills] if isinstance(skills, str) else skills,
                "experience_range": experience,
            }
        except Exception as e:
            log.warning(f"HelloWork: job {job_id}: {e}")
            return {}
