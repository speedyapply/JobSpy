from __future__ import annotations

import random
import time
from itertools import cycle

from bs4 import BeautifulSoup
from curl_cffi import requests

from jobspy.model import (
    Scraper,
    ScraperInput,
    Site,
    JobPost,
    JobResponse,
    JobType,
    DescriptionFormat,
)
from jobspy.util import create_logger, markdown_converter, plain_converter
from jobspy.wellfound.constant import role_slug_map
from jobspy.wellfound.util import (
    extract_next_data,
    get_apollo_state,
    parse_compensation_string,
    parse_location_names,
    slugify,
    timestamp_to_date,
)

log = create_logger("Wellfound")


class WellFound(Scraper):
    base_url = "https://wellfound.com"
    delay = 2
    band_delay = 3

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        """
        Initializes WellFound with curl_cffi TLS impersonation ('chrome124')
        for DataDome anti-bot bypass and proxy rotation support.
        """
        super().__init__(Site.WELLFOUND, proxies=proxies, ca_cert=ca_cert)
        self.scraper_input = None
        self.proxy_cycle = None
        if isinstance(proxies, str):
            self.proxy_cycle = cycle([self._format_proxy(proxies)])
        elif isinstance(proxies, list) and proxies:
            self.proxy_cycle = cycle([self._format_proxy(p) for p in proxies])

    @staticmethod
    def _format_proxy(proxy: str) -> dict:
        if (
            proxy.startswith("http://")
            or proxy.startswith("https://")
            or proxy.startswith("socks5://")
        ):
            return {"http": proxy, "https": proxy}
        return {"http": f"http://{proxy}", "https": f"http://{proxy}"}

    def _get_proxy(self) -> dict | None:
        if self.proxy_cycle:
            return next(self.proxy_cycle)
        return None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """
        Scrapes Wellfound for jobs matching scraper_input criteria using curl_cffi.
        Parses __NEXT_DATA__ JSON payload from response HTML, falling back to HTML parsing if needed.
        """
        self.scraper_input = scraper_input
        job_list: list[JobPost] = []
        seen_ids: set[str] = set()
        page = 1
        results_wanted = (
            scraper_input.results_wanted if scraper_input.results_wanted else 15
        )

        urls_to_try = self._build_search_urls(scraper_input, page)

        while len(job_list) < results_wanted:
            log.info(f"Fetching Wellfound jobs page {page}")

            html = None
            for url in urls_to_try:
                try:
                    proxy = self._get_proxy()
                    req_kwargs = {
                        "impersonate": "chrome124",
                        "timeout": getattr(scraper_input, "request_timeout", 60),
                    }
                    if proxy:
                        req_kwargs["proxies"] = proxy

                    response = requests.get(url, **req_kwargs)

                    if response.status_code == 200:
                        html = response.text
                        log.info(f"Successfully fetched {url}")
                        break
                    elif response.status_code == 403:
                        log.warning(
                            f"Wellfound returned status 403 (DataDome block) for {url}"
                        )
                    else:
                        log.warning(
                            f"Wellfound returned status {response.status_code} for {url}"
                        )
                except Exception as e:
                    log.warning(f"Request failed for {url}: {str(e)}")

            if not html:
                log.error(
                    "Failed to fetch any Wellfound URL. "
                    "DataDome anti-bot protection blocked the request. "
                    "Pass rotating residential proxies via the 'proxies' parameter."
                )
                break

            # 1. Try __NEXT_DATA__ JSON parsing
            jobs_on_page = self._parse_next_data(html, scraper_input)

            # 2. HTML Fallback parsing if __NEXT_DATA__ returned no jobs
            if not jobs_on_page:
                log.info("Attempting HTML fallback parsing...")
                jobs_on_page = self._parse_html_fallback(html, scraper_input)

            if not jobs_on_page:
                log.info(f"No jobs found on page {page}. Ending pagination.")
                break

            initial_count = len(job_list)
            for job in jobs_on_page:
                if job.id not in seen_ids:
                    seen_ids.add(job.id)
                    job_list.append(job)
                    if len(job_list) >= results_wanted:
                        break

            if len(job_list) == initial_count:
                log.info(f"No new jobs found on page {page}. Ending pagination.")
                break

            page += 1
            urls_to_try = self._build_search_urls(scraper_input, page)
            time.sleep(random.uniform(self.delay, self.delay + self.band_delay))

        job_list = job_list[:results_wanted]
        return JobResponse(jobs=job_list)

    def _build_search_urls(self, scraper_input: ScraperInput, page: int) -> list[str]:
        base = self.base_url
        urls = []
        page_suffix = f"?page={page}" if page > 1 else ""

        if scraper_input.location:
            location_slug = slugify(scraper_input.location)
            urls.append(f"{base}/location/{location_slug}{page_suffix}")

        if scraper_input.search_term:
            term_lower = scraper_input.search_term.lower().strip()
            role_slug = role_slug_map.get(term_lower)
            if role_slug:
                urls.append(f"{base}/role/l/{role_slug}{page_suffix}")
            else:
                urls.append(
                    f"{base}/role/l/{slugify(scraper_input.search_term)}{page_suffix}"
                )

        urls.append(f"{base}/jobs{page_suffix}")
        return urls

    def _parse_next_data(
        self, html: str, scraper_input: ScraperInput | None = None
    ) -> list[JobPost]:
        next_data = extract_next_data(html)
        if not next_data:
            return []

        apollo_state = get_apollo_state(next_data)
        if not apollo_state:
            return []

        return self._parse_apollo_jobs(apollo_state, scraper_input)

    def _parse_apollo_jobs(
        self, apollo_data: dict, scraper_input: ScraperInput | None = None
    ) -> list[JobPost]:
        job_posts = []
        # Build startup index from StartupResult or Startup entities
        startup_map = {}
        for key, val in apollo_data.items():
            if (
                key.startswith("Startup:") or key.startswith("StartupResult:")
            ) and isinstance(val, dict):
                startup_map[key] = val
                # Link highlight listings back to startup
                highlighted = val.get("highlightedJobListings", [])
                for item in highlighted:
                    if isinstance(item, dict) and "__ref" in item:
                        startup_map[item["__ref"]] = val

        for key, value in apollo_data.items():
            if not (
                key.startswith("JobListing:")
                or key.startswith("JobListingSearchResult:")
            ):
                continue
            if not isinstance(value, dict):
                continue

            try:
                job_post = self._map_listing_to_job_post(
                    value, apollo_data, startup_map, key
                )
                if job_post:
                    if scraper_input and scraper_input.search_term:
                        search_lower = scraper_input.search_term.lower()
                        words = search_lower.split()
                        combined_text = f"{(job_post.title or '')} {(job_post.company_name or '')} {(job_post.description or '')}".lower()
                        if not any(word in combined_text for word in words):
                            continue
                    job_posts.append(job_post)
            except Exception as e:
                log.debug(f"Error parsing job listing {key}: {str(e)}")
                continue

        return job_posts

    def _map_listing_to_job_post(
        self, listing: dict, apollo_data: dict, startup_map: dict, entity_key: str
    ) -> JobPost | None:
        listing_id = listing.get("id")
        title = listing.get("title")
        slug = listing.get("slug", "")

        if not listing_id or not title:
            return None

        job_url = f"{self.base_url}/jobs/{listing_id}-{slug}"

        # Company mapping
        startup = None
        startup_ref = listing.get("startup")
        if startup_ref and isinstance(startup_ref, dict) and "__ref" in startup_ref:
            startup = apollo_data.get(startup_ref["__ref"])
        if not startup:
            startup = startup_map.get(entity_key)

        company_name = startup.get("name") if startup else None
        company_logo = startup.get("logoUrl") if startup else None
        company_slug = startup.get("slug") if startup else None
        company_url = (
            f"{self.base_url}/company/{company_slug}" if company_slug else None
        )

        # Remote status
        is_remote = listing.get("remote", False)
        remote_config = listing.get("remoteConfig")
        if (
            remote_config
            and isinstance(remote_config, dict)
            and "__ref" in remote_config
        ):
            remote_entity = apollo_data.get(remote_config["__ref"])
            if remote_entity:
                kind = remote_entity.get("kind", "")
                if kind == "REMOTE_ONLY":
                    is_remote = True
                elif kind == "ONSITE":
                    is_remote = False

        # Location mapping
        location_names = listing.get("locationNames", [])
        location = parse_location_names(location_names, is_remote=is_remote)

        # Job type mapping
        raw_job_type = listing.get("jobType", "")
        job_types = self._map_job_type(raw_job_type)

        # Description
        description = listing.get("description")
        if description and self.scraper_input:
            fmt = getattr(
                self.scraper_input,
                "description_format",
                DescriptionFormat.MARKDOWN,
            )
            if fmt == DescriptionFormat.MARKDOWN:
                description = markdown_converter(description)
            elif fmt == DescriptionFormat.PLAIN:
                description = plain_converter(description)

        # Compensation
        compensation = parse_compensation_string(listing.get("compensation"))

        # Date posted
        date_posted = timestamp_to_date(listing.get("liveStartAt"))

        job_id = f"wf-{listing_id}"

        return JobPost(
            id=job_id,
            title=title,
            company_name=company_name,
            company_url=company_url,
            company_logo=company_logo,
            job_url=job_url,
            location=location,
            is_remote=is_remote,
            description=description,
            job_type=job_types,
            compensation=compensation,
            date_posted=date_posted,
        )

    def _map_job_type(self, job_type_str: str) -> list[JobType] | None:
        if not job_type_str:
            return None
        j_lower = job_type_str.lower().replace("-", "")
        if "fulltime" in j_lower:
            return [JobType.FULL_TIME]
        elif "parttime" in j_lower:
            return [JobType.PART_TIME]
        elif "contract" in j_lower:
            return [JobType.CONTRACT]
        elif "intern" in j_lower:
            return [JobType.INTERNSHIP]
        return None

    def _parse_html_fallback(
        self, html: str, scraper_input: ScraperInput | None = None
    ) -> list[JobPost]:
        """
        Fallback parser using BeautifulSoup HTML tag search if __NEXT_DATA__ is missing or empty.
        """
        soup = BeautifulSoup(html, "html.parser")
        job_posts = []

        # Look for job card elements or containers
        job_cards = soup.find_all(
            "div",
            class_=lambda c: c
            and any(k in (c or "").lower() for k in ["job", "listing", "startup"]),
        )
        for card in job_cards:
            title_elem = card.find(
                ["h2", "h3", "h4", "a"],
                class_=lambda c: c and "title" in (c or "").lower(),
            )
            if not title_elem:
                title_elem = card.find("a", href=lambda h: h and "/jobs/" in h)

            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            href = title_elem.get("href", "") if title_elem.name == "a" else ""
            job_url = f"{self.base_url}{href}" if href.startswith("/") else href

            company_elem = card.find(
                ["span", "div", "a"],
                class_=lambda c: c and "company" in (c or "").lower(),
            )
            company_name = company_elem.get_text(strip=True) if company_elem else None

            job_id = f"wf-{hash(job_url)}" if job_url else f"wf-{hash(title)}"

            job_posts.append(
                JobPost(
                    id=job_id,
                    title=title,
                    company_name=company_name,
                    location=None,
                    job_url=job_url or f"{self.base_url}/jobs",
                )
            )

        return job_posts