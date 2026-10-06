from __future__ import annotations

import random
import re
import time
from datetime import date
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from jobspy.linkedin.constant import (
    currencies,
    empty_page,
    headers,
    jobs_per_page,
    max_results,
    pay_intervals,
)
from jobspy.linkedin.util import criteria, is_job_remote, parse_location
from jobspy.model import (
    JobPost,
    JobResponse,
    Compensation,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.util import (
    format_description,
    get_enum_from_job_type,
    create_session,
    remove_attributes,
    create_logger,
)

log = create_logger("LinkedIn")


class LinkedIn(Scraper):
    base_url = "https://www.linkedin.com"
    delay = 3
    band_delay = 4

    def __init__(
        self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        super().__init__(
            Site.LINKEDIN, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent
        )
        self.session = create_session(
            proxies=self.proxies,
            ca_cert=ca_cert,
            is_tls=False,
            clear_cookies=True,
        )
        self.session.headers.update(headers)
        if user_agent:
            self.session.headers["user-agent"] = user_agent
        self.scraper_input = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        for name in ("is_remote", "job_type"):
            if getattr(scraper_input, name):
                log.warning(f"LinkedIn: {name} isn't supported, ignoring it")
        params = self._search_params()
        job_list: list[JobPost] = []
        seen = set()
        first_start = start = scraper_input.offset
        page = 1

        while len(job_list) < scraper_input.results_wanted and start < max_results:
            if start > first_start:
                time.sleep(random.uniform(self.delay, self.delay + self.band_delay))
            log.info(f"search page: {page}")
            try:
                response = self.session.get(
                    f"{self.base_url}/jobs-guest/jobs/api/seeMoreJobPostings/search",
                    params={**params, "start": start},
                )
                if response.status_code != 200:
                    log.error(f"LinkedIn response status code {response.status_code}")
                    break
            except Exception as e:
                log.error(f"LinkedIn: {e}")
                break

            soup = BeautifulSoup(response.text, "html.parser")
            job_cards = soup.find_all(class_="base-search-card")
            if not job_cards:
                if response.text.strip() != empty_page:
                    log.error("LinkedIn: unexpected page with no jobs (blocked?)")
                elif start:
                    log.warning(
                        f"LinkedIn: empty page at start={start} (the end of the results, or throttled)"
                    )
                break

            new_cards = []
            for job_card in job_cards:
                job_id = job_card.get("data-entity-urn", "").split(":")[-1]
                if job_id and job_id not in seen:
                    seen.add(job_id)
                    new_cards.append((job_id, job_card))

            for job_id, job_card in new_cards:
                try:
                    job_post = self._process_job(job_card, job_id)
                except Exception as e:
                    log.warning(f"skipping job: {e}")
                    continue
                job_list.append(job_post)
                if len(job_list) >= scraper_input.results_wanted:
                    break

            if not new_cards or len(job_cards) < jobs_per_page:
                break
            start += jobs_per_page
            page += 1

        return JobResponse(jobs=job_list)

    def _search_params(self) -> dict:
        scraper_input = self.scraper_input
        params = {
            "keywords": scraper_input.search_term,
            "location": scraper_input.location,
            "distance": scraper_input.distance,
        }
        if scraper_input.easy_apply:
            params["f_AL"] = "true"
        if scraper_input.linkedin_company_ids:
            params["f_C"] = ",".join(map(str, scraper_input.linkedin_company_ids))
        if scraper_input.hours_old:
            params["f_TPR"] = f"r{scraper_input.hours_old * 3600}"
        return {name: value for name, value in params.items() if value is not None}

    def _process_job(self, job_card: Tag, job_id: str) -> JobPost:
        title = job_card.find("h3", class_="base-search-card__title").get_text(strip=True)

        company_tag = job_card.find("h4", class_="base-search-card__subtitle")
        company_link = company_tag.find("a", href=True)
        location = parse_location(
            job_card.find("span", class_="job-search-card__location").text.strip()
        )
        try:
            date_posted = date.fromisoformat(job_card.find("time")["datetime"])
        except (TypeError, KeyError, ValueError):
            date_posted = None
        job_details = (
            self._fetch_details(job_id) if self.scraper_input.fetch_description else {}
        )

        return JobPost(
            id=f"li-{job_id}",
            title=title,
            company_name=company_tag.get_text(strip=True),
            company_url=company_link["href"].split("?")[0] if company_link else None,
            location=location,
            is_remote=is_job_remote(title, location),
            date_posted=date_posted,
            job_url=f"{self.base_url}/jobs/view/{job_id}",
            **job_details,
        )

    @staticmethod
    def _parse_salary(text: str) -> Compensation | None:
        """ "$117,000.00/yr - $234,000.00/yr" """
        match = re.fullmatch(
            r"([^\d\s]+) ?([\d,]+\.\d\d)(/\w+) - [^\d\s]+ ?([\d,]+\.\d\d)/\w+",
            " ".join(text.split()),
        )
        if not match:
            return None
        currency, low, interval, high = match.groups()
        return Compensation(
            interval=pay_intervals.get(interval),
            min_amount=float(low.replace(",", "")),
            max_amount=float(high.replace(",", "")),
            currency=currencies.get(currency, currency),
        )

    def _fetch_details(self, job_id: str) -> dict:
        """
        The job page's description, pay, logo and criteria; empty when the page can't be read
        """
        try:
            response = self.session.get(f"{self.base_url}/jobs/view/{job_id}")
        except Exception as e:
            log.warning(f"LinkedIn: job {job_id}: {e}")
            return {}
        if response.status_code != 200:
            log.warning(
                f"LinkedIn response status code {response.status_code} for job {job_id}"
            )
            return {}
        path = urlparse(response.url).path
        if not path.startswith("/jobs/view/"):
            log.warning(f"LinkedIn: job {job_id}: redirected to {path}")
            return {}

        soup = BeautifulSoup(response.text, "html.parser")
        div_content = soup.find("div", class_="show-more-less-html__markup")
        description, emails = format_description(
            remove_attributes(div_content).prettify(formatter="html") if div_content else None,
            self.scraper_input.description_format,
        )
        logo_image = soup.find("img", class_="artdeco-entity-image")
        salary_tag = soup.find("div", class_="compensation__salary")
        compensation = self._parse_salary(salary_tag.get_text()) if salary_tag else None
        employment_type = criteria(soup, "Employment type")
        job_type = (
            get_enum_from_job_type(employment_type.lower().replace("-", ""))
            if employment_type
            else None
        )
        job_level = criteria(soup, "Seniority level")
        return {
            "description": description,
            "emails": emails,
            "compensation": compensation,
            "job_type": [job_type] if job_type else None,
            "job_level": job_level.lower() if job_level else None,
            "job_function": criteria(soup, "Job function"),
            "company_industry": criteria(soup, "Industries"),
            "company_logo": logo_image.get("data-delayed-url") if logo_image else None,
        }
