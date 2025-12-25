from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, date
from typing import Optional
from urllib.parse import urljoin, quote

from bs4 import BeautifulSoup
from bs4.element import Tag

from jobspy.exception import InternshalaException
from jobspy.internshala.constant import headers
from jobspy.internshala.util import (
    find_job_cards,
    parse_location,
    parse_posted_ago,
    parse_stipend,
)
from jobspy.model import (
    JobPost,
    Location,
    JobResponse,
    Country,
    Compensation,
    DescriptionFormat,
    Scraper,
    ScraperInput,
    Site,
    JobType,
)
from jobspy.util import (
    extract_emails_from_text,
    markdown_converter,
    plain_converter,
    create_session,
    create_logger,
)

log = create_logger("Internshala")


class Internshala(Scraper):
    base_url = "https://internshala.com"
    delay = 2
    band_delay = 3

    def __init__(
        self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        super().__init__(Site.INTERNSHALA, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)
        self.session = create_session(
            proxies=self.proxies,
            ca_cert=ca_cert,
            is_tls=False,
            has_retry=True,
            delay=5,
            clear_cookies=True,
        )
        self.session.headers.update(headers)
        if user_agent:
            self.session.headers["user-agent"] = user_agent
        self.scraper_input: ScraperInput | None = None
        self.country = Country.INDIA

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.country = Country.INDIA
        job_list: list[JobPost] = []
        seen_urls: set[str] = set()

        hours_limit = scraper_input.hours_old
        posted_cutoff: Optional[datetime] = None
        if hours_limit is not None:
            posted_cutoff = datetime.utcnow() - timedelta(hours=hours_limit)

        results_wanted = scraper_input.results_wanted or 15

        query = (scraper_input.internshala_search_term or scraper_input.search_term or "").strip()
        paths: list[tuple[str, str]]
        if query:
            encoded_query = quote(query.lower(), safe="")
            paths = [
                ("internship", f"/internships/keywords-{encoded_query}/"),
                ("job", f"/jobs/keywords-{encoded_query}/"),
            ]
        else:
            paths = [
                ("internship", "/internships/"),
                ("job", "/jobs/"),
            ]

        for kind, path in paths:
            if len(job_list) >= results_wanted:
                break

            page = 1
            while len(job_list) < results_wanted:
                url = urljoin(self.base_url, path)
                if page > 1:
                    if url.endswith("/"):
                        url = f"{url}page-{page}/"
                    else:
                        url = f"{url}/page-{page}/"

                log.info(f"Internshala: fetching {url}")
                try:
                    resp = self.session.get(url, timeout=getattr(scraper_input, "request_timeout", 60))
                except Exception as e:
                    log.error(f"Internshala request failed for {url}: {e}")
                    raise InternshalaException(str(e))

                if resp.status_code not in range(200, 400):
                    log.warning(f"Internshala response status code {resp.status_code} for {url}")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = find_job_cards(soup)
                if not cards:
                    log.info("Internshala: no more job cards found")
                    break

                page_added = 0
                for card in cards:
                    employment_type = (card.get("employment_type") or "").strip().lower()
                    if kind == "job" and employment_type and employment_type != "job":
                        continue
                    if kind == "internship" and employment_type and employment_type != "internship":
                        continue

                    try:
                        job_post = self._process_card(card, posted_cutoff, kind)
                    except InternshalaException as e:
                        log.error(f"Internshala error while processing card: {e}")
                        continue
                    except Exception as e:
                        log.error(f"Unexpected error while processing Internshala card: {e}")
                        continue

                    if not job_post:
                        continue

                    if job_post.job_url in seen_urls:
                        continue

                    seen_urls.add(job_post.job_url)
                    job_list.append(job_post)
                    page_added += 1

                    if len(job_list) >= results_wanted:
                        break

                if page_added == 0:
                    break

                page += 1
                time.sleep(random.uniform(self.delay, self.delay + self.band_delay))

        return JobResponse(jobs=job_list[:results_wanted])

    def _process_card(self, card: Tag, posted_cutoff: Optional[datetime], kind: str) -> Optional[JobPost]:

        link = card.find("a", href=lambda h: h and ("/internship/detail/" in h or "/job/detail/" in h))
        if not link:
            return None

        job_url = urljoin(self.base_url, link.get("href"))
        title = link.get_text(strip=True) or "Internship"

        company_name: Optional[str] = None

        company_el = card.select_one("p.company-name")
        if company_el:
            company_name = company_el.get_text(strip=True) or None

        if not company_name:
            company_name_el = card.find("a", href=lambda h: h and "/company/" in h)
            if company_name_el:
                company_name = company_name_el.get_text(strip=True) or None

        if not company_name:
            full_text = card.get_text("\n", strip=True)
            if title in full_text:
                after_title = full_text.split(title, 1)[1]
            else:
                after_title = full_text

            lines = [ln.strip() for ln in after_title.split("\n") if ln.strip()]
            for ln in lines:
                lower_ln = ln.lower()
                if any(
                    skip in lower_ln
                    for skip in [
                        "actively hiring",
                        "be an early applicant",
                        "work from home",
                        "internships in india",
                        "apply now",
                    ]
                ):
                    continue
                if ln and (ln[0].isascii() is False):
                    continue
                company_name = ln
                break

        location_text: Optional[str] = None
        is_remote: bool = False

        loc_el = card.select_one(".row-1-item.locations span a")
        if loc_el:
            location_text = loc_el.get_text(strip=True) or None
            if location_text and location_text.lower() in {"work from home", "remote"}:
                is_remote = True

        if not location_text:
            location_text, is_remote = parse_location(card)

        posted_ago = parse_posted_ago(card)
        date_posted: Optional[date] = None
        if posted_ago is not None:
            dt_posted = datetime.utcnow() - posted_ago
            date_posted = dt_posted.date()
            if posted_cutoff and dt_posted < posted_cutoff:
                return None

        stipend_comp = parse_stipend(card)

        description: str | None = None
        if self.scraper_input and self.scraper_input.linkedin_fetch_description:
            description = self._fetch_description(job_url)

        if description:
            if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
                description = markdown_converter(description)
            elif self.scraper_input.description_format == DescriptionFormat.PLAIN:
                description = plain_converter(description)

        emails = extract_emails_from_text(description or "") if description else None

        location_obj = Location(city=location_text, country=self.country) if location_text else Location(country=self.country)

        if kind == "job":
            job_types = [JobType.FULL_TIME]
            listing_type = "job"
        else:
            job_types = [JobType.INTERNSHIP]
            listing_type = "internship"

        job_post = JobPost(
            id=f"internshala-{hash(job_url)}",
            title=title,
            company_name=company_name,
            job_url=job_url,
            location=location_obj,
            description=description,
            job_type=job_types,
            compensation=stipend_comp,
            date_posted=date_posted,
            emails=emails,
            is_remote=is_remote,
            listing_type=listing_type,
        )
        return job_post

    def _fetch_description(self, job_url: str) -> Optional[str]:
        try:
            resp = self.session.get(job_url, timeout=self.scraper_input.request_timeout if self.scraper_input else 60)
        except Exception as e:
            log.error(f"Internshala description fetch failed for {job_url}: {e}")
            return None

        if resp.status_code not in range(200, 400):
            log.warning(f"Internshala description fetch status {resp.status_code} for {job_url}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        about_header = soup.find(lambda tag: tag.name in ["h2", "h3"] and "about the internship" in tag.get_text(strip=True).lower())
        if about_header:
            desc_parts: list[str] = []
            for sib in about_header.find_all_next():
                if sib.name in ("h2", "h3") and sib is not about_header:
                    break
                desc_parts.append(sib.get_text(" ", strip=True))
            text = "\n".join(p for p in desc_parts if p)
            return text or None

        main = soup.find("div", id="internship_detail") or soup.body
        return main.get_text(" ", strip=True) if main else None
