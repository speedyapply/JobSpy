from __future__ import annotations

import os
import random
import re
import time
import unicodedata
from datetime import datetime
from html import escape

from pydantic import BaseModel, ConfigDict

from jobspy.infojobs.constant import (
    base_url,
    default_delay,
    delay_env,
    headers,
    last_week,
    pay_intervals,
    province_aliases,
    provinces,
    remote_id,
    remote_label,
    search_url,
    spain_id,
    week_hours,
)
from jobspy.model import (
    Compensation,
    Country,
    JobPost,
    JobType,
    Location,
    Scraper,
    ScraperInput,
)
from jobspy.util import (
    TLSRotating,
    check_status,
    create_session,
    description_fields,
    utc_date,
)


class SalaryRange(BaseModel):
    min: float | None = None
    max: float | None = None


class Salary(BaseModel):
    range: SalaryRange | None = None
    period: str | None = None
    currency: str | None = None


class Offer(BaseModel):
    """One offer of the search results the site's own pages load"""

    model_config = ConfigDict(extra="ignore")

    code: str
    title: str
    link: str
    description: str | None = None
    city: str | None = None
    contractType: str | None = None
    workday: str | None = None
    teleworking: str | None = None
    salary: Salary | None = None
    publishedAt: str | None = None
    companyName: str | None = None
    companyLogo: str | None = None
    companyLink: str | None = None
    executive: bool | None = None


class Navigation(BaseModel):
    totalPages: int = 1


class SearchPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    offers: list[dict[str, object]] = []
    navigation: Navigation = Navigation()


class InfoJobs(Scraper):
    """Spain, through the search the infojobs.net pages call. INFOJOBS_DELAY sets the
    seconds between requests: "4", or "3-6" for a random pause in that range."""

    def scrape(self, scraper_input: ScraperInput) -> list[JobPost]:
        self.scraper_input = scraper_input
        self.delay = self._delay()
        self.session = create_session(
            TLSRotating(scraper_input.proxies), scraper_input, headers=headers
        )
        params = self._search_params()
        city = self._city_filter()
        job_list: list[JobPost] = []
        seen: set[str] = set()
        page = 1
        skipped = 0

        while len(job_list) < scraper_input.results_wanted:
            if page > 1:
                time.sleep(random.uniform(*self.delay))
            self.log.info(f"search page: {page}")
            try:
                response = self.session.get(search_url, params=params | {"page": page})
                check_status(response)
                try:
                    data = response.json()
                except ValueError:
                    raise ValueError(
                        "the site answered with a page instead of results: its bot "
                        f"protection may be blocking you, raise {delay_env} or retry "
                        "later"
                    ) from None
                result = SearchPage.model_validate(data)
            except Exception as e:
                self.fail(str(e))
                break

            offers = []
            for item in result.offers:
                try:
                    offers.append(Offer.model_validate(item))
                except Exception as e:
                    self.log.warning(f"skipping job: {e}")
            new_offers = [offer for offer in offers if offer.code not in seen]
            seen.update(offer.code for offer in offers)
            too_old = 0
            for offer in new_offers:
                if self._too_old(offer):
                    too_old += 1
                    continue
                if not self._matches(offer, city):
                    continue
                if skipped < scraper_input.offset:
                    skipped += 1
                    continue
                try:
                    job_list.append(self._process_job(offer))
                except Exception as e:
                    self.log.warning(f"skipping job {offer.code}: {e}")
                    continue
                if len(job_list) >= scraper_input.results_wanted:
                    break

            # sorted by date: a page of only old offers means the rest are older
            all_old = bool(new_offers) and too_old == len(new_offers)
            if not new_offers or all_old or page >= result.navigation.totalPages:
                break
            page += 1

        return job_list

    def _delay(self) -> tuple[float, float]:
        """INFOJOBS_DELAY: "4" -> (4, 4); "3-6" -> (3, 6)"""
        value = os.environ.get(delay_env, "").strip()
        if not value:
            return default_delay
        try:
            low, _, high = value.replace(",", "-").partition("-")
            delay = (float(low), float(high or low))
        except ValueError:
            self.warn(f"{delay_env}={value!r} isn't seconds like 4 or 3-6, using 3-6")
            return default_delay
        return (min(delay), max(delay))

    @staticmethod
    def _slug(text: str) -> str:
        """ "A Coruña" -> "a-coruna", the form the site's location links take"""
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

    def _province(self) -> int | None:
        if not self.scraper_input.location:
            return None
        key = self._slug(self.scraper_input.location.split(",")[0])
        return provinces.get(province_aliases.get(key, key))

    def _city_filter(self) -> str | None:
        """A location that isn't a province or Spain is matched against each job's city"""
        location = self.scraper_input.location
        if not location or self._province() is not None:
            return None
        key = self._slug(location.split(",")[0])
        return None if key in ("espana", "spain") else key

    def _search_params(self) -> dict[str, str | int]:
        scraper_input = self.scraper_input
        params: dict[str, str | int | None] = {
            "keyword": scraper_input.search_term,
            "countryIds": spain_id,
            "onlyForeignCountry": "false",
            "sortBy": "PUBLICATION_DATE",
            "provinceIds": self._province(),
        }
        if scraper_input.is_remote:
            params["teleworkingIds"] = remote_id
        if scraper_input.hours_old and scraper_input.hours_old <= week_hours:
            params["sinceDate"] = last_week
        if scraper_input.distance not in (None, 50):
            self.warn("distance isn't supported, ignoring it")
        if scraper_input.easy_apply:
            self.warn("easy_apply isn't supported, ignoring it")
        return {
            name: value for name, value in params.items() if value not in (None, "")
        }

    @staticmethod
    def _parse_time(published: str | None) -> float | None:
        """ "2026-11-13T16:26:29Z" -> its Unix time"""
        if not published:
            return None
        try:
            return datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None

    def _too_old(self, offer: Offer) -> bool:
        hours_old = self.scraper_input.hours_old
        published = self._parse_time(offer.publishedAt)
        return bool(
            hours_old and published and time.time() - published > hours_old * 3600
        )

    @staticmethod
    def _job_types(offer: Offer) -> list[JobType]:
        contract = (offer.contractType or "").lower()
        workday = (offer.workday or "").lower()
        job_types = []
        if "completa" in workday:
            job_types.append(JobType.FULL_TIME)
        if "parcial" in workday or "parcial" in contract:
            job_types.append(JobType.PART_TIME)
        if "determinada" in contract or "discontinuo" in contract:
            job_types.append(JobType.TEMPORARY)
        if "autónomo" in contract or "mercantil" in contract:
            job_types.append(JobType.CONTRACT)
        if "formativo" in contract or "prácticas" in contract:
            job_types.append(JobType.INTERNSHIP)
        return job_types

    def _matches(self, offer: Offer, city: str | None) -> bool:
        scraper_input = self.scraper_input
        if scraper_input.is_remote and offer.teleworking != remote_label:
            return False
        if city and city not in self._slug(offer.city or ""):
            return False
        job_type = scraper_input.job_type
        return not job_type or job_type in self._job_types(offer)

    def _process_job(self, offer: Offer) -> JobPost:
        salary = Compensation()
        if offer.salary and offer.salary.range:
            low, high = offer.salary.range.min, offer.salary.range.max
            if low is not None or high is not None:
                salary = Compensation(
                    interval=pay_intervals.get(offer.salary.period or ""),
                    min_amount=low if low is not None else high,
                    max_amount=high if high is not None else low,
                    currency=offer.salary.currency or "EUR",
                )
        link = offer.link.split("?")[0]
        if link.startswith("//"):
            link = f"https:{link}"
        elif link.startswith("/"):
            link = f"{base_url}{link}"
        html = (
            "".join(
                f"<p>{escape(line.strip())}</p>"
                for line in offer.description.splitlines()
                if line.strip()
            )
            if offer.description
            else None
        )
        job_post = JobPost(
            id=f"ij-{offer.code}",
            title=offer.title,
            company=offer.companyName,
            location=Location(city=offer.city, country=Country.SPAIN),
            job_url=link,
            date_posted=utc_date(self._parse_time(offer.publishedAt)),
            job_type=self._job_types(offer) or None,
            is_remote=offer.teleworking == remote_label,
            work_from_home_type=offer.teleworking,
            job_level="Directivo" if offer.executive else None,
            company_url=offer.companyLink,
            company_logo=offer.companyLogo,
            **salary.model_dump(),
        )
        return job_post.model_copy(
            update=description_fields(html, self.scraper_input.description_format)
        )
