from __future__ import annotations

import math
from datetime import datetime

from jobspy.model import (
    Compensation,
    CompensationInterval,
    Country,
    DescriptionFormat,
    JobPost,
    JobResponse,
    JobType,
    Location,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.util import create_logger, create_session, format_description

log = create_logger("Freehire")


class Freehire(Scraper):
    base_url = "https://freehire.me/api/v1"
    search_url = f"{base_url}/jobs/search"
    agent_search_url = f"{base_url}/agent/jobs/search"
    cities_url = f"{base_url}/geo/cities"

    employment_types = {
        "full_time": JobType.FULL_TIME,
        "part_time": JobType.PART_TIME,
        "contract": JobType.CONTRACT,
        "internship": JobType.INTERNSHIP,
    }
    salary_periods = {
        "year": CompensationInterval.YEARLY,
        "month": CompensationInterval.MONTHLY,
        "day": CompensationInterval.DAILY,
        "hour": CompensationInterval.HOURLY,
    }

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        super().__init__(
            Site.FREEHIRE,
            proxies=proxies,
            ca_cert=ca_cert,
            user_agent=user_agent,
        )
        self.session = None
        self.scraper_input = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        self.scraper_input = scraper_input
        self.session = create_session(
            proxies=self.proxies, ca_cert=self.ca_cert, is_tls=False
        )
        self.session.headers.update(
            {
                "User-Agent": self.user_agent
                or "python-jobspy (+https://github.com/speedyapply/JobSpy)"
            }
        )

        endpoint = (
            self.agent_search_url
            if scraper_input.fetch_description
            else self.search_url
        )
        params = self._search_params()
        if scraper_input.location:
            city = self._resolve_city(scraper_input.location)
            if city is None:
                return JobResponse(jobs=[])
            params["cities"] = city

        jobs = []
        seen = set()
        offset = max(0, scraper_input.offset)
        while len(jobs) < scraper_input.results_wanted and offset < 10000:
            limit = min(
                100,
                scraper_input.results_wanted - len(jobs),
                10000 - offset,
            )
            payload = self._request_json(
                endpoint, params | {"limit": limit, "offset": offset}
            )
            if not payload:
                break

            results = payload.get("data")
            if not isinstance(results, list):
                log.warning("Freehire returned an invalid jobs response")
                break

            metadata = payload.get("meta") or {}
            if ignored_params := metadata.get("ignored_params"):
                log.warning("Freehire ignored search parameters: %s", ignored_params)

            previous_count = len(seen)
            for job in results:
                if not isinstance(job, dict):
                    log.warning("Skipping malformed Freehire job")
                    continue
                slug = job.get("public_slug")
                if not isinstance(slug, str) or not slug or slug in seen:
                    continue
                seen.add(slug)
                try:
                    jobs.append(self._process_job(job))
                except Exception as error:
                    log.warning("Skipping Freehire job: %s", error)
                if len(jobs) >= scraper_input.results_wanted:
                    break

            offset += len(results)
            if len(seen) == previous_count or len(results) < limit:
                break
            if metadata.get("total") is not None and offset >= metadata["total"]:
                break

        return JobResponse(jobs=jobs)

    def _search_params(self) -> dict:
        params = {"is_tech": "tech"}
        if self.scraper_input.search_term:
            params["q"] = self.scraper_input.search_term

        if self.scraper_input.is_remote:
            params["work_mode"] = "remote"

        if job_type := self.scraper_input.job_type:
            employment_type = {
                JobType.FULL_TIME: "full_time",
                JobType.PART_TIME: "part_time",
                JobType.CONTRACT: "contract",
                JobType.INTERNSHIP: "internship",
            }.get(job_type)
            if employment_type:
                params["employment_type"] = employment_type

        if not self.scraper_input.location:
            country_code = self._country_code(self.scraper_input.country)
            if country_code:
                params["countries"] = country_code

        if hours_old := self.scraper_input.hours_old:
            if hours_old >= 1:
                params["posted_within_days"] = math.ceil(hours_old / 24)

        if self.scraper_input.fetch_description:
            description_format = self.scraper_input.description_format
            if isinstance(description_format, DescriptionFormat):
                description_format = description_format.value
            if description_format:
                params["description_format"] = (
                    "text" if description_format == "plain" else description_format
                )

        return params

    def _resolve_city(self, location: str) -> str | None:
        city = location.split(",", 1)[0].strip()
        params = {"q": city}
        if country_code := self._country_code(self.scraper_input.country):
            params["country"] = country_code

        payload = self._request_json(self.cities_url, params)
        matches = payload.get("data", []) if payload else []
        for match in matches:
            if isinstance(match, dict) and isinstance(match.get("value"), str):
                if match["value"].casefold() == city.casefold():
                    return match["value"]
        log.warning("Freehire could not resolve city '%s'", location)
        return None

    def _request_json(self, url: str, params: dict) -> dict | None:
        try:
            response = self.session.get(url, params=params)
            if response.status_code != 200:
                log.warning("Freehire returned HTTP %s", response.status_code)
                return None
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        except Exception as error:
            log.warning("Freehire request failed: %s", error)
            return None

    @staticmethod
    def _country_code(country: Country | None) -> str | None:
        if country in (None, Country.US_CANADA, Country.WORLDWIDE):
            return None
        country_value = country.value[1]
        country_code = country_value.rsplit(":", 1)[-1].lower()
        return country_code if len(country_code) == 2 else None

    def _process_job(self, job: dict) -> JobPost:
        slug = job["public_slug"]
        apply_url = job.get("url")
        enrichment = job.get("enrichment") or {}
        work_mode = job.get("work_mode")
        posted_at = job.get("posted_at")
        if posted_at:
            posted_date = datetime.fromisoformat(
                posted_at.replace("Z", "+00:00")
            ).date()
        else:
            posted_date = None

        compensation = None
        salary_min = enrichment.get("salary_min")
        salary_max = enrichment.get("salary_max")
        if salary_min is not None or salary_max is not None:
            compensation = Compensation(
                interval=self.salary_periods.get(enrichment.get("salary_period")),
                min_amount=salary_min,
                max_amount=salary_max,
                currency=enrichment.get("salary_currency"),
            )

        location_text = job.get("location")
        description = job.get("description")
        if self.scraper_input and not self.scraper_input.fetch_description:
            description, _ = format_description(
                description, self.scraper_input.description_format
            )
        return JobPost(
            id=f"freehire-{slug}",
            title=job["title"],
            company_name=job["company"],
            job_url=apply_url or f"https://freehire.me/jobs/{slug}",
            job_url_direct=apply_url,
            location=Location(city=location_text) if location_text else None,
            description=description,
            date_posted=posted_date,
            job_type=(
                [self.employment_types[enrichment["employment_type"]]]
                if enrichment.get("employment_type") in self.employment_types
                else None
            ),
            compensation=compensation,
            is_remote={"remote": True, "onsite": False}.get(work_mode),
            work_from_home_type=work_mode.title() if work_mode else None,
            job_level=enrichment.get("seniority"),
            company_industry=(
                ", ".join(enrichment["domains"]) if enrichment.get("domains") else None
            ),
            skills=job.get("skills") or None,
        )
