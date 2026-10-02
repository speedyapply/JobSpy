from __future__ import annotations

import math
import random
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from jobspy.linkedin.constant import currencies, headers, pay_intervals
from jobspy.linkedin.util import (
    is_job_remote,
    job_type_code,
    parse_job_type,
    parse_job_level,
    parse_company_industry
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
)
from jobspy.util import (
    extract_emails_from_text,
    markdown_converter,
    plain_converter,
    create_session,
    remove_attributes,
    create_logger,
)

log = create_logger("LinkedIn")


class LinkedIn(Scraper):
    base_url = "https://www.linkedin.com"
    delay = 3
    band_delay = 4
    jobs_per_page = 25

    def __init__(
        self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        """
        Initializes LinkedInScraper with the LinkedIn job search url
        """
        super().__init__(Site.LINKEDIN, proxies=proxies, ca_cert=ca_cert)
        self.session = create_session(
            proxies=self.proxies,
            ca_cert=ca_cert,
            is_tls=False,
            clear_cookies=True,
        )
        self.session.headers.update(headers)
        self.scraper_input = None
        self.country = "worldwide"

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """
        Scrapes LinkedIn for jobs with scraper_input criteria
        :param scraper_input:
        :return: job_response
        """
        self.scraper_input = scraper_input
        job_list: list[JobPost] = []
        seen_ids = set()
        start = scraper_input.offset // 10 * 10 if scraper_input.offset else 0
        request_count = 0
        seconds_old = (
            scraper_input.hours_old * 3600 if scraper_input.hours_old else None
        )
        continue_search = (
            lambda: len(job_list) < scraper_input.results_wanted and start < 1000
        )
        while continue_search():
            request_count += 1
            log.info(
                f"search page: {request_count} / {math.ceil(scraper_input.results_wanted / 10)}"
            )
            params = {
                "keywords": scraper_input.search_term,
                "location": scraper_input.location,
                "distance": scraper_input.distance,
                "f_WT": 2 if scraper_input.is_remote else None,
                "f_JT": (
                    job_type_code(scraper_input.job_type)
                    if scraper_input.job_type
                    else None
                ),
                "pageNum": 0,
                "start": start,
                "f_AL": "true" if scraper_input.easy_apply else None,
                "f_C": (
                    ",".join(map(str, scraper_input.linkedin_company_ids))
                    if scraper_input.linkedin_company_ids
                    else None
                ),
            }
            if seconds_old is not None:
                params["f_TPR"] = f"r{seconds_old}"

            params = {k: v for k, v in params.items() if v is not None}
            try:
                response = self.session.get(
                    f"{self.base_url}/jobs-guest/jobs/api/seeMoreJobPostings/search?",
                    params=params,
                )
                if response.status_code != 200:
                    log.error(f"LinkedIn response status code {response.status_code}")
                    break
            except Exception as e:
                log.error(f"LinkedIn: {e}")
                break

            soup = BeautifulSoup(response.text, "html.parser")
            job_cards = soup.find_all("div", class_="base-search-card")
            if len(job_cards) == 0:
                break

            for job_card in job_cards:
                href_tag = job_card.find("a", class_="base-card__full-link")
                if href_tag and "href" in href_tag.attrs:
                    href = href_tag.attrs["href"].split("?")[0]
                    job_id = href.split("-")[-1]

                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    try:
                        fetch_desc = scraper_input.fetch_description
                        job_post = self._process_job(job_card, job_id, fetch_desc)
                        if job_post:
                            job_list.append(job_post)
                        if not continue_search():
                            break
                    except Exception as e:
                        log.warning(f"skipping job: {e}")

            if continue_search():
                time.sleep(random.uniform(self.delay, self.delay + self.band_delay))
                start += len(job_cards)

        job_list = job_list[: scraper_input.results_wanted]
        return JobResponse(jobs=job_list)

    def _process_job(
        self, job_card: Tag, job_id: str, full_descr: bool
    ) -> Optional[JobPost]:
        title_tag = job_card.find("span", class_="sr-only")
        title = title_tag.get_text(strip=True) if title_tag else "N/A"

        company_tag = job_card.find("h4", class_="base-search-card__subtitle")
        company_a_tag = company_tag.find("a") if company_tag else None
        company_url = (
            urlunparse(urlparse(company_a_tag.get("href"))._replace(query=""))
            if company_a_tag and company_a_tag.has_attr("href")
            else ""
        )
        company = company_a_tag.get_text(strip=True) if company_a_tag else "N/A"

        metadata_card = job_card.find("div", class_="base-search-card__metadata")
        location = self._get_location(metadata_card)

        datetime_tag = (
            metadata_card.find("time", class_="job-search-card__listdate")
            if metadata_card
            else None
        )
        if not datetime_tag and metadata_card:
            datetime_tag = metadata_card.find(
                "time", class_="job-search-card__listdate--new"
            )
        date_posted = None
        if datetime_tag and "datetime" in datetime_tag.attrs:
            datetime_str = datetime_tag["datetime"]
            try:
                date_posted = datetime.strptime(datetime_str, "%Y-%m-%d")
            except Exception:
                date_posted = None
        job_details = {}
        if full_descr:
            job_details = self._get_job_details(job_id)

        return JobPost(
            id=f"li-{job_id}",
            title=title,
            company_name=company,
            company_url=company_url,
            location=location,
            is_remote=is_job_remote(title, location),
            date_posted=date_posted,
            job_url=f"{self.base_url}/jobs/view/{job_id}",
            compensation=job_details.get("compensation"),
            job_type=job_details.get("job_type"),
            job_level=job_details.get("job_level"),
            company_industry=job_details.get("company_industry"),
            description=job_details.get("description"),
            emails=extract_emails_from_text(job_details.get("description")),
            company_logo=job_details.get("company_logo"),
            job_function=job_details.get("job_function"),
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

    def _get_job_details(self, job_id: str) -> dict:
        """
        Retrieves job description and other job details by going to the job page url
        :param job_page_url:
        :return: dict
        """
        try:
            response = self.session.get(f"{self.base_url}/jobs/view/{job_id}")
            response.raise_for_status()
        except Exception:
            return {}
        if "linkedin.com/signup" in response.url:
            return {}

        soup = BeautifulSoup(response.text, "html.parser")
        div_content = soup.find(
            "div", class_=lambda x: x and "show-more-less-html__markup" in x
        )
        description = None
        if div_content is not None:
            div_content = remove_attributes(div_content)
            description = div_content.prettify(formatter="html")
            if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
                description = markdown_converter(description)
            elif self.scraper_input.description_format == DescriptionFormat.PLAIN:
                description = plain_converter(description)
        h3_tag = soup.find(
            "h3", string=lambda text: text and "Job function" in text.strip()
        )

        job_function = None
        if h3_tag:
            job_function_span = h3_tag.find_next(
                "span", class_="description__job-criteria-text"
            )
            if job_function_span:
                job_function = job_function_span.text.strip()

        company_logo = (
            logo_image.get("data-delayed-url")
            if (logo_image := soup.find("img", {"class": "artdeco-entity-image"}))
            else None
        )
        salary_tag = soup.find("div", class_="compensation__salary")
        compensation = self._parse_salary(salary_tag.get_text()) if salary_tag else None
        return {
            "description": description,
            "compensation": compensation,
            "job_level": parse_job_level(soup),
            "company_industry": parse_company_industry(soup),
            "job_type": parse_job_type(soup),
            "company_logo": company_logo,
            "job_function": job_function,
        }

    def _get_location(self, metadata_card: Optional[Tag]) -> Location:
        """
        Extracts the location data from the job metadata card.
        :param metadata_card
        :return: location
        """
        location = Location(country=Country.from_string(self.country))
        if metadata_card is not None:
            location_tag = metadata_card.find(
                "span", class_="job-search-card__location"
            )
            location_string = location_tag.text.strip() if location_tag else "N/A"
            parts = location_string.split(", ")
            if len(parts) == 1 and location_tag:
                location = Location(
                    city=location_string, country=Country.from_string(self.country)
                )
            elif len(parts) == 2:
                city, state = parts
                location = Location(
                    city=city,
                    state=state,
                    country=Country.from_string(self.country),
                )
            elif len(parts) == 3:
                city, state, country = parts
                location = Location(city=city, state=state, country=country)
        return location
