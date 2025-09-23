# __init__.py
from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from jobspy.exception import BDJobsException
from jobspy.bdjobs.constant import headers, search_params
from jobspy.bdjobs.util import (
    parse_location,
    parse_date,
    find_job_listings,
    is_job_remote,
)
from jobspy.model import (
    JobPost,
    Location,
    JobResponse,
    Country,
    Scraper,
    ScraperInput,
    Site,
    DescriptionFormat,
)
from jobspy.util import (
    extract_emails_from_text,
    create_session,
    create_logger,
    remove_attributes,
    markdown_converter,
)

log = create_logger("BDJobs")


class BDJobs(Scraper):
    base_url = "https://jobs.bdjobs.com"
    search_url = "https://jobs.bdjobs.com/jobsearch.asp"
    delay = 2
    band_delay = 3

    def __init__(
        self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        """
        Initializes BDJobsScraper with the BDJobs job search url
        """
        super().__init__(Site.BDJOBS, proxies=proxies, ca_cert=ca_cert)
        self.session = create_session(
            proxies=self.proxies,
            ca_cert=ca_cert,
            is_tls=False,
            has_retry=True,
            delay=5,
            clear_cookies=True,
        )
        self.session.headers.update(headers)
        self.scraper_input = None
        self.country = "bangladesh"

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """
        Scrapes BDJobs for jobs with scraper_input criteria
        :param scraper_input:
        :return: job_response
        """
        self.scraper_input = scraper_input
        job_list: list[JobPost] = []
        seen_ids = set()
        page = 1
        request_count = 0

        # Set up search parameters
        params = search_params.copy()
        params["txtsearch"] = scraper_input.search_term

        continue_search = lambda: len(job_list) < scraper_input.results_wanted

        while continue_search():
            request_count += 1
            log.info(f"search page: {request_count}")

            try:
                # Add page parameter if needed
                if page > 1:
                    params["pg"] = page

                response = self.session.get(
                    self.search_url,
                    params=params,
                    timeout=getattr(scraper_input, "request_timeout", 60),
                )

                if response.status_code != 200:
                    log.error(f"BDJobs response status code {response.status_code}")
                    break

                soup = BeautifulSoup(response.text, "html.parser")
                job_cards = find_job_listings(soup)

                if not job_cards or len(job_cards) == 0:
                    log.info("No more job listings found")
                    break

                log.info(f"Found {len(job_cards)} job cards on page {page}")

                for job_card in job_cards:
                    try:
                        job_post = self._process_job(job_card)
                        if job_post and job_post.id not in seen_ids:
                            seen_ids.add(job_post.id)
                            job_list.append(job_post)

                            if not continue_search():
                                break
                    except Exception as e:
                        log.error(f"Error processing job card: {str(e)}")

                page += 1
                # Add delay between requests
                time.sleep(random.uniform(self.delay, self.delay + self.band_delay))

            except Exception as e:
                log.error(f"Error during scraping: {str(e)}")
                break

        job_list = job_list[: scraper_input.results_wanted]
        return JobResponse(jobs=job_list)

    def _process_job(self, job_card: Tag) -> Optional[JobPost]:
        """
        Processes a job card element into a JobPost object
        :param job_card: Job card element
        :return: JobPost object
        """
        try:
            # Extract job ID and URL
            job_link = job_card.find("a", href=lambda h: h and "jobdetail" in h.lower())
            if not job_link:
                return None

            job_url = job_link.get("href")
            if not job_url.startswith("http"):
                job_url = urljoin(self.base_url, job_url)

            # Extract job ID from URL
            job_id = (
                job_url.split("jobid=")[-1].split("&")[0]
                if "jobid=" in job_url
                else f"bdjobs-{hash(job_url)}"
            )

            # Extract title
            title = job_link.get_text(strip=True)
            if not title:
                title_elem = job_card.find(
                    ["h2", "h3", "h4", "strong", "div"],
                    class_=lambda c: c and "job-title-text" in c,
                )
                title = title_elem.get_text(strip=True) if title_elem else "N/A"

            # Extract company name - IMPROVED
            company_elem = job_card.find(
                ["span", "div"],
                class_=lambda c: c and "comp-name-text" in (c or "").lower(),
            )
            if company_elem:
                company_name = company_elem.get_text(strip=True)
            else:
                # Try alternative selectors
                company_elem = job_card.find(
                    ["span", "div"],
                    class_=lambda c: c
                    and any(
                        term in (c or "").lower()
                        for term in ["company", "org", "comp-name"]
                    ),
                )
                company_name = (
                    company_elem.get_text(strip=True) if company_elem else "N/A"
                )

            # Extract location
            location_elem = job_card.find(
                ["span", "div"],
                class_=lambda c: c and "locon-text-d" in (c or "").lower(),
            )
            if not location_elem:
                location_elem = job_card.find(
                    ["span", "div"],
                    class_=lambda c: c
                    and any(
                        term in (c or "").lower()
                        for term in ["location", "area", "locon"]
                    ),
                )
            location_text = (
                location_elem.get_text(strip=True)
                if location_elem
                else "Dhaka, Bangladesh"
            )

            # Create Location object
            location = parse_location(location_text, self.country)

            # Extract date posted
            date_elem = job_card.find(
                ["span", "div"],
                class_=lambda c: c
                and any(
                    term in (c or "").lower()
                    for term in ["date", "deadline", "published"]
                ),
            )
            date_posted = None
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                date_posted = parse_date(date_text)

            # Check if job is remote
            is_remote = is_job_remote(title, location=location)

            # Create job post object
            job_post = JobPost(
                id=job_id,
                title=title,
                company_name=company_name,  # Use company_name instead of company
                location=location,
                date_posted=date_posted,
                job_url=job_url,
                is_remote=is_remote,
                site=self.site,
            )

            # Always fetch description for BDJobs
            job_details = self._get_job_details(job_url)
            job_post.description = job_details.get("description", "")
            job_post.job_type = job_details.get("job_type", "")

            return job_post
        except Exception as e:
            log.error(f"Error in _process_job: {str(e)}")
            return None

    def _get_job_details(self, job_url: str) -> Dict[str, Any]:
        """
        Gets detailed job information from the job page
        :param job_url: Job page URL
        :return: Dictionary with job details
        """
        try:
            response = self.session.get(job_url, timeout=60)
            if response.status_code != 200:
                return {}

            soup = BeautifulSoup(response.text, "html.parser")

            # Find job description - IMPROVED based on correct.py
            description = ""

            # Try to find the job content div first (as in correct.py)
            job_content_div = soup.find("div", class_="jobcontent")
            if job_content_div:
                # Look for responsibilities section
                responsibilities_heading = job_content_div.find(
                    "h4", id="job_resp"
                ) or job_content_div.find(
                    ["h4", "h5"], string=lambda s: s and "responsibilities" in s.lower()
                )
                if responsibilities_heading:
                    responsibilities_elements = []
                    # Find all following elements until the next heading or hr
                    for sibling in responsibilities_heading.find_next_siblings():
                        if sibling.name in ["hr", "h4", "h5"]:
                            break
                        if sibling.name == "ul":
                            responsibilities_elements.extend(
                                li.get_text(separator=" ", strip=True)
                                for li in sibling.find_all("li")
                            )
                        elif sibling.name == "p":
                            responsibilities_elements.append(
                                sibling.get_text(separator=" ", strip=True)
                            )

                description = (
                    "\n".join(responsibilities_elements)
                    if responsibilities_elements
                    else ""
                )

            # If no description found yet, try the original approach
            if not description:
                description_elem = soup.find(
                    ["div", "section"],
                    class_=lambda c: c
                    and any(
                        term in (c or "").lower()
                        for term in ["job-description", "details", "requirements"]
                    ),
                )
                if description_elem:
                    description_elem = remove_attributes(description_elem)
                    description = description_elem.prettify(formatter="html")
                    if (
                        hasattr(self.scraper_input, "description_format")
                        and self.scraper_input.description_format
                        == DescriptionFormat.MARKDOWN
                    ):
                        description = markdown_converter(description)

            # Extract job type
            job_type_elem = soup.find(
                ["span", "div"],
                string=lambda s: s
                and any(
                    term in (s or "").lower()
                    for term in ["job type", "employment type"]
                ),
            )
            job_type = None
            if job_type_elem:
                job_type_text = job_type_elem.find_next(["span", "div"]).get_text(
                    strip=True
                )
                job_type = job_type_text if job_type_text else None

            # Extract company industry
            industry_elem = soup.find(
                ["span", "div"], string=lambda s: s and "industry" in (s or "").lower()
            )
            company_industry = None
            if industry_elem:
                industry_text = industry_elem.find_next(["span", "div"]).get_text(
                    strip=True
                )
                company_industry = industry_text if industry_text else None

            return {
                "description": description,
                "job_type": job_type,
                "company_industry": company_industry,
            }

        except Exception as e:
            log.error(f"Error getting job details: {str(e)}")
            return {}
