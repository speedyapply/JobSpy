from __future__ import annotations

import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from bs4 import BeautifulSoup

from jobspy.ziprecruiter.constant import headers, get_cookie_data
from jobspy.util import (
    extract_emails_from_text,
    create_session,
    markdown_converter,
    remove_attributes,
    create_logger,
)
from jobspy.model import (
    JobPost,
    Compensation,
    Location,
    JobResponse,
    Country,
    DescriptionFormat,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.ziprecruiter.util import get_job_type_enum, add_params

log = create_logger("ZipRecruiter")


class ZipRecruiter(Scraper):
    base_url = "https://www.ziprecruiter.com"
    api_url = "https://api.ziprecruiter.com"

    def __init__(
        self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        """
        Initializes ZipRecruiterScraper with the ZipRecruiter job search url
        """
        super().__init__(Site.ZIP_RECRUITER, proxies=proxies)

        self.scraper_input = None
        self.session = create_session(proxies=proxies, ca_cert=ca_cert)
        self.session.headers.update(headers)
        self._get_cookies()

        self.delay = 5
        self.jobs_per_page = 20
        self.seen_urls = set()

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """
        Scrapes ZipRecruiter for jobs with scraper_input criteria.
        :param scraper_input: Information about job search criteria.
        :return: JobResponse containing a list of jobs.
        """
        self.scraper_input = scraper_input
        job_list: list[JobPost] = []
        continue_token = None

        max_pages = math.ceil(scraper_input.results_wanted / self.jobs_per_page)
        for page in range(1, max_pages + 1):
            if len(job_list) >= scraper_input.results_wanted:
                break
            if page > 1:
                time.sleep(self.delay)
            log.info(f"search page: {page} / {max_pages}")
            jobs_on_page, continue_token = self._find_jobs_in_page(
                scraper_input, continue_token
            )
            if jobs_on_page:
                job_list.extend(jobs_on_page)
            else:
                break
            if not continue_token:
                break
        return JobResponse(jobs=job_list[: scraper_input.results_wanted])

    def _find_jobs_in_page(
        self, scraper_input: ScraperInput, continue_token: str | None = None
    ) -> tuple[list[JobPost], str | None]:
        """
        Scrapes a page of ZipRecruiter for jobs with scraper_input criteria
        :param scraper_input:
        :param continue_token:
        :return: jobs found on page
        """
        jobs_list = []
        params = add_params(scraper_input)
        if continue_token:
            params["continue_from"] = continue_token
        try:
            res = self.session.get(f"{self.api_url}/jobs-app/jobs", params=params)
            if res.status_code not in range(200, 400):
                if res.status_code == 429:
                    err = "429 Response - Blocked by ZipRecruiter for too many requests"
                else:
                    err = f"ZipRecruiter response status code {res.status_code}"
                    err += f" with response: {res.text}"  # ZipRecruiter likely not available in EU
                log.error(err)
                return jobs_list, ""
        except Exception as e:
            if "Proxy responded with" in str(e):
                log.error(f"Indeed: Bad proxy")
            else:
                log.error(f"Indeed: {str(e)}")
            return jobs_list, ""

        res_data = res.json()
        jobs_list = res_data.get("jobs", [])
        next_continue_token = res_data.get("continue", None)
        with ThreadPoolExecutor(max_workers=self.jobs_per_page) as executor:
            job_results = [executor.submit(self._process_job, job) for job in jobs_list]

        job_list = list(filter(None, (result.result() for result in job_results)))
        return job_list, next_continue_token

    def _process_job(self, job: dict) -> JobPost | None:
        """
        Processes an individual job dict from the response
        """
        title = job.get("name")
        job_url = f"{self.base_url}/jobs//j?lvk={job['listing_key']}"
        if job_url in self.seen_urls:
            return
        self.seen_urls.add(job_url)

        description = job.get("job_description", "").strip()
        listing_type = job.get("buyer_type", "")
        description = (
            markdown_converter(description)
            if self.scraper_input.description_format == DescriptionFormat.MARKDOWN
            else description
        )
        company = job.get("hiring_company", {}).get("name")
        country_value = "usa" if job.get("job_country") == "US" else "canada"
        country_enum = Country.from_string(country_value)

        location = Location(
            city=job.get("job_city"), state=job.get("job_state"), country=country_enum
        )
        job_type = get_job_type_enum(
            job.get("employment_type", "").replace("_", "").lower()
        )
        date_posted = datetime.fromisoformat(job["posted_time"].rstrip("Z")).date()
        comp_interval = job.get("compensation_interval")
        comp_interval = "yearly" if comp_interval == "annual" else comp_interval
        comp_min = int(job["compensation_min"]) if "compensation_min" in job else None
        comp_max = int(job["compensation_max"]) if "compensation_max" in job else None
        comp_currency = job.get("compensation_currency")
        description_full, job_url_direct = self._get_descr(job_url)

        return JobPost(
            id=f'zr-{job["listing_key"]}',
            title=title,
            company_name=company,
            location=location,
            job_type=job_type,
            compensation=Compensation(
                interval=comp_interval,
                min_amount=comp_min,
                max_amount=comp_max,
                currency=comp_currency,
            ),
            date_posted=date_posted,
            job_url=job_url,
            description=description_full if description_full else description,
            emails=extract_emails_from_text(description) if description else None,
            job_url_direct=job_url_direct,
            listing_type=listing_type,
        )

    def _get_descr(self, job_url):
        res = self.session.get(job_url, allow_redirects=True)
        description_full = job_url_direct = None
        if res.ok:
            soup = BeautifulSoup(res.text, "html.parser")
            job_descr_div = soup.find("div", class_="job_description")
            company_descr_section = soup.find("section", class_="company_description")
            job_description_clean = (
                remove_attributes(job_descr_div).prettify(formatter="html")
                if job_descr_div
                else ""
            )
            company_description_clean = (
                remove_attributes(company_descr_section).prettify(formatter="html")
                if company_descr_section
                else ""
            )
            description_full = job_description_clean + company_description_clean

            try:
                script_tag = soup.find("script", type="application/json")
                if script_tag:
                    job_json = json.loads(script_tag.string)
                    job_url_val = job_json["model"].get("saveJobURL", "")
                    m = re.search(r"job_url=(.+)", job_url_val)
                    if m:
                        job_url_direct = m.group(1)
            except:
                job_url_direct = None

            if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
                description_full = markdown_converter(description_full)

        return description_full, job_url_direct

    def _get_cookies(self):
        """
        Sends a session event to the API with device properties.
        """
        url = f"{self.api_url}/jobs-app/event"
        self.session.post(url, data=get_cookie_data)
