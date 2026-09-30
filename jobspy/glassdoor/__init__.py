from __future__ import annotations

import json
from typing import Tuple
from urllib.parse import quote
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from jobspy.glassdoor.constant import query_template, headers
from jobspy.glassdoor.util import (
    get_cursor_for_page,
    parse_compensation,
    parse_location,
)
from jobspy.util import (
    extract_emails_from_text,
    create_logger,
    create_session,
    markdown_converter,
)
from jobspy.exception import GlassdoorException
from jobspy.model import (
    JobPost,
    JobResponse,
    DescriptionFormat,
    Scraper,
    ScraperInput,
    Site,
)

log = create_logger("Glassdoor")


class Glassdoor(Scraper):
    def __init__(
        self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        """
        Initializes GlassdoorScraper with the Glassdoor job search url
        """
        site = Site(Site.GLASSDOOR)
        super().__init__(site, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)

        self.base_url = None
        self.session = None
        self.scraper_input = None
        self.jobs_per_page = 30
        self.max_pages = 30
        self.seen_urls = set()

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """
        Scrapes Glassdoor for jobs with scraper_input criteria.
        :param scraper_input: Information about job search criteria.
        :return: JobResponse containing a list of jobs.
        """
        self.scraper_input = scraper_input
        self.scraper_input.results_wanted = min(900, scraper_input.results_wanted)
        self.base_url = self.scraper_input.country.get_glassdoor_url()

        self.session = create_session(
            proxies=self.proxies, ca_cert=self.ca_cert, has_retry=True
        )
        self.session.headers.update(headers)
        if self.user_agent:
            self.session.headers["user-agent"] = self.user_agent

        location_id, location_type = self._get_location(
            scraper_input.location, scraper_input.is_remote
        )
        if location_type is None:
            log.error(f"Glassdoor: location '{scraper_input.location}' not parsed")
            return JobResponse(jobs=[])
        job_list: list[JobPost] = []
        cursor = None

        range_start = 1 + (scraper_input.offset // self.jobs_per_page)
        tot_pages = (scraper_input.results_wanted // self.jobs_per_page) + 2
        range_end = min(tot_pages, self.max_pages + 1)
        for page in range(range_start, range_end):
            log.info(f"search page: {page} / {range_end - 1}")
            try:
                jobs, cursor = self._fetch_jobs_page(
                    location_id, location_type, page, cursor
                )
                job_list.extend(jobs)
                if not jobs or len(job_list) >= scraper_input.results_wanted:
                    job_list = job_list[: scraper_input.results_wanted]
                    break
            except Exception as e:
                log.error(f"Glassdoor: {str(e)}")
                break
        return JobResponse(jobs=job_list)

    def _fetch_jobs_page(
        self,
        location_id: int,
        location_type: str,
        page_num: int,
        cursor: str | None,
    ) -> Tuple[list[JobPost], str | None]:
        """
        Scrapes a page of Glassdoor for jobs with scraper_input criteria
        """
        jobs = []
        try:
            payload = self._add_payload(location_id, location_type, page_num, cursor)
            response = self.session.post(
                f"{self.base_url}/graph",
                timeout_seconds=15,
                data=payload,
            )
            if response.status_code != 200:
                exc_msg = f"bad response status code: {response.status_code}"
                raise GlassdoorException(exc_msg)
            res_json = response.json()[0]
            # every page also has harmless errors on other fields (jobsPageSeoData)
            if not (res_json.get("data") or {}).get("jobListings"):
                errors = res_json.get("errors")
                raise ValueError(f"Error encountered in API response: {errors}")
        except Exception as e:
            log.error(f"Glassdoor: {str(e)}")
            return jobs, None

        # only the jobs still needed: with fetch_description each one costs a request
        remaining = self.scraper_input.results_wanted - len(self.seen_urls)
        jobs_data = res_json["data"]["jobListings"]["jobListings"][:remaining]

        with ThreadPoolExecutor(max_workers=self.jobs_per_page) as executor:
            futures = [executor.submit(self._process_job, job) for job in jobs_data]
            for future in as_completed(futures):
                try:
                    job_post = future.result()
                except Exception as e:
                    log.warning(f"skipping job: {e}")
                    continue
                if job_post:
                    jobs.append(job_post)

        return jobs, get_cursor_for_page(
            res_json["data"]["jobListings"]["paginationCursors"], page_num + 1
        )

    def _process_job(self, job_data):
        """
        Processes a single job; fetches its description if fetch_description is set.
        """
        job_id = job_data["jobview"]["job"]["listingId"]
        job_url = f"{self.base_url}/job-listing/j?jl={job_id}"
        if job_url in self.seen_urls:
            return None
        job = job_data["jobview"]
        title = job["job"]["jobTitleText"]
        company_name = job["header"]["employerNameFromSearch"]
        company_id = job_data["jobview"]["header"]["employer"]["id"]
        location_name = job["header"].get("locationName", "")
        location_type = job["header"].get("locationType", "")
        age_in_days = job["header"].get("ageInDays")
        is_remote, location = False, None
        date_posted = (
            (datetime.now() - timedelta(days=age_in_days)).date()
            if age_in_days is not None
            else None
        )

        if location_type == "S":
            is_remote = True
        else:
            location = parse_location(location_name)

        compensation = parse_compensation(job["header"])
        description = None
        if self.scraper_input.fetch_description:
            try:
                description = self._fetch_job_description(job_id)
            except Exception:
                pass
        company_url = f"{self.base_url}/Overview/W-EI_IE{company_id}.htm"
        company_logo = (
            job_data["jobview"].get("overview", {}).get("squareLogoUrl", None)
        )
        listing_type = (
            job_data["jobview"]
            .get("header", {})
            .get("adOrderSponsorshipLevel", "")
            .lower()
        )
        self.seen_urls.add(job_url)

        return JobPost(
            id=f"gd-{job_id}",
            title=title,
            company_url=company_url if company_id else None,
            company_name=company_name,
            date_posted=date_posted,
            job_url=job_url,
            location=location,
            compensation=compensation,
            is_remote=is_remote,
            description=description,
            emails=extract_emails_from_text(description) if description else None,
            company_logo=company_logo,
            listing_type=listing_type,
        )

    def _fetch_job_description(self, job_id):
        """
        Fetches the job description for a single job ID.
        """
        url = f"{self.base_url}/graph"
        body = [
            {
                "operationName": "JobDetailQuery",
                "variables": {
                    "jl": job_id,
                    "queryString": "q",
                    "pageTypeEnum": "SERP",
                },
                "query": """
                query JobDetailQuery($jl: Long!, $queryString: String, $pageTypeEnum: PageTypeEnum) {
                    jobview: jobView(
                        listingId: $jl
                        contextHolder: {queryString: $queryString, pageTypeEnum: $pageTypeEnum}
                    ) {
                        job {
                            description
                            __typename
                        }
                        __typename
                    }
                }
                """,
            }
        ]
        res = self.session.post(url, json=body)
        if res.status_code != 200:
            return None
        data = res.json()[0]
        desc = data["data"]["jobview"]["job"]["description"]
        if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
            desc = markdown_converter(desc)
        return desc

    def _autocomplete_url(self, term: str) -> str:
        return (
            f"{self.base_url}/autocomplete/location"
            f"?locationTypeFilters=CITY,STATE,COUNTRY&caller=jobs&term={quote(term)}"
        )

    def _get_location(self, location: str, is_remote: bool) -> (int, str):
        if not location or is_remote:
            # search/description requests need the cookies autocomplete sets
            self.session.get(self._autocomplete_url("remote"))
            return "11047", "STATE"  # remote options
        res = self.session.get(self._autocomplete_url(location))
        if res.status_code != 200:
            if res.status_code == 429:
                err = "429 Response - Blocked by Glassdoor for too many requests"
                log.error(err)
                return None, None
            else:
                log.error(f"Glassdoor response status code {res.status_code}")
                return None, None
        items = res.json()

        if not items:
            return None, None
        location_type = items[0]["locationType"]
        location_type = {"C": "CITY", "S": "STATE", "N": "COUNTRY"}.get(
            location_type, location_type
        )
        return int(items[0]["locationId"]), location_type

    def _add_payload(
        self,
        location_id: int,
        location_type: str,
        page_num: int,
        cursor: str | None = None,
    ) -> str:
        fromage = None
        if self.scraper_input.hours_old:
            fromage = max(self.scraper_input.hours_old // 24, 1)
        filter_params = []
        if self.scraper_input.easy_apply:
            filter_params.append({"filterKey": "applicationType", "values": "1"})
        if fromage:
            filter_params.append({"filterKey": "fromAge", "values": str(fromage)})
        payload = {
            "operationName": "JobSearchResultsQuery",
            "variables": {
                "excludeJobListingIds": [],
                "filterParams": filter_params,
                "keyword": self.scraper_input.search_term,
                "numJobsToShow": 30,
                "locationType": location_type,
                "locationId": int(location_id),
                "parameterUrlInput": f"IL.0,12_I{location_type}{location_id}",
                "pageNumber": page_num,
                "pageCursor": cursor,
                "fromage": fromage,
                "sort": "date",
            },
            "query": query_template,
        }
        if self.scraper_input.job_type:
            payload["variables"]["filterParams"].append(
                {"filterKey": "jobType", "values": self.scraper_input.job_type.value[0]}
            )
        return json.dumps([payload])
