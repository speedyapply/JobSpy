from __future__ import annotations

import re
from datetime import datetime

from jobspy.model import (
    Scraper,
    ScraperInput,
    Site,
    JobPost,
    JobResponse,
    Location,
    Country,
    JobType,
    Compensation,
    CompensationInterval,
    DescriptionFormat,
)
from jobspy.solidjobs.constant import (
    api_url,
    default_campaign,
    divisions,
    headers,
    max_page_size,
)
from jobspy.util import (
    create_logger,
    create_session,
    markdown_converter,
    plain_converter,
)

log = create_logger("SolidJobs")


class SolidJobs(Scraper):
    """Scraper for the Polish job board SOLID.Jobs (https://solid.jobs).

    Uses the public job offers API (https://solid.jobs/api-ofert-pracy) which
    requires no authentication. SOLID.Jobs has no free text search endpoint, so
    `search_term` is applied client-side against the title, company and skills.
    """

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.SOLIDJOBS, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent
        )
        self.scraper_input = None
        self.session = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.session = create_session(
            proxies=self.proxies, ca_cert=self.ca_cert, is_tls=False, has_retry=True
        )
        self.session.headers.update(headers)
        if self.user_agent:
            self.session.headers["User-Agent"] = self.user_agent

        results_wanted = scraper_input.results_wanted or 15
        job_list: list[JobPost] = []
        seen_keys: set[str] = set()

        for division in divisions:
            if len(job_list) >= results_wanted:
                break
            self._scrape_division(division, results_wanted, job_list, seen_keys)

        return JobResponse(jobs=job_list[:results_wanted])

    def _scrape_division(
        self,
        division: str,
        results_wanted: int,
        job_list: list[JobPost],
        seen_keys: set[str],
    ) -> None:
        page_index = 0
        while len(job_list) < results_wanted:
            data = self._fetch_offers(division, page_index)
            if not data:
                break
            offers = data.get("jobs") or []
            if not offers:
                break
            for offer in offers:
                key = offer.get("jobOfferKey")
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                if not self._matches_filters(offer):
                    continue
                job_post = self._process_offer(offer)
                if job_post:
                    job_list.append(job_post)
                    if len(job_list) >= results_wanted:
                        return
            if page_index + 1 >= data.get("totalPages", 0):
                break
            page_index += 1

    def _fetch_offers(self, division: str, page_index: int) -> dict | None:
        # The public API ignores its documented filter params (city, minSalary,
        # experienceLevel), so only division + pagination are sent and every
        # other filter is applied client-side in _matches_filters.
        params = {
            "campaign": default_campaign,
            "pageSize": max_page_size,
            "pageIndex": page_index,
        }
        try:
            response = self.session.get(
                f"{api_url}/{division}",
                params=params,
                timeout=self.scraper_input.request_timeout,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            log.error(f"SolidJobs: Error fetching division {division} - {str(e)}")
            return None

    def _matches_filters(self, offer: dict) -> bool:
        if self.scraper_input.is_remote and not offer.get("isRemote"):
            return False
        if self.scraper_input.job_type:
            offer_job_type = self._map_job_type(offer.get("contractTime"))
            if offer_job_type != self.scraper_input.job_type:
                return False
        location = self.scraper_input.location
        if location:
            offer_locations = " ".join(offer.get("locations") or []).lower()
            if location.lower() not in offer_locations:
                return False
        search_term = self.scraper_input.search_term
        if search_term:
            skills = offer.get("skills") or []
            haystack = " ".join(
                [
                    offer.get("title") or "",
                    offer.get("company") or "",
                    " ".join(skill.get("name", "") for skill in skills),
                ]
            ).lower()
            # No free text endpoint, so require every search token to be present.
            tokens = search_term.lower().split()
            if not all(token in haystack for token in tokens):
                return False
        return True

    def _process_offer(self, offer: dict) -> JobPost | None:
        title = offer.get("title")
        job_url = offer.get("url")
        if not title or not job_url:
            return None

        locations = offer.get("locations") or []
        location = Location(
            city=locations[0] if locations else None,
            country=Country.POLAND,
        )

        job_type = self._map_job_type(offer.get("contractTime"))

        return JobPost(
            id=f"solidjobs-{offer.get('jobOfferKey')}",
            title=title,
            company_name=offer.get("company"),
            location=location,
            job_url=job_url,
            description=self._format_description(offer.get("description")),
            company_logo=offer.get("companyLogoUrl"),
            job_type=[job_type] if job_type else None,
            compensation=self._map_compensation(offer.get("salary")),
            date_posted=self._parse_date(offer.get("validFrom")),
            is_remote=offer.get("isRemote"),
            job_level=offer.get("experienceLevel"),
            skills=[
                skill.get("name")
                for skill in offer.get("skills") or []
                if skill.get("name")
            ]
            or None,
        )

    def _format_description(self, description: str | None) -> str | None:
        if not description:
            return None
        if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
            return markdown_converter(description)
        if self.scraper_input.description_format == DescriptionFormat.PLAIN:
            return plain_converter(description)
        return description

    @staticmethod
    def _map_job_type(contract_time: str | None) -> JobType | None:
        return {
            "full_time": JobType.FULL_TIME,
            "part_time": JobType.PART_TIME,
        }.get(contract_time)

    @staticmethod
    def _map_compensation(salary: dict | None) -> Compensation | None:
        if not salary:
            return None
        interval = (
            CompensationInterval.MONTHLY
            if salary.get("period") == "Month"
            else None
        )
        return Compensation(
            interval=interval,
            min_amount=salary.get("from"),
            max_amount=salary.get("to"),
            currency=salary.get("currency") or "PLN",
        )

    @staticmethod
    def _parse_date(value: str | None):
        if not value:
            return None
        # The API returns 4-7 fractional-second digits and may use 'Z';
        # datetime.fromisoformat only accepts 3 or 6 digits (and no 'Z') on
        # Python < 3.11, so pad/truncate fractional seconds to exactly 6.
        value = value.replace("Z", "+00:00")
        value = re.sub(
            r"\.(\d+)", lambda m: "." + m.group(1)[:6].ljust(6, "0"), value
        )
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
