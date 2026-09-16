from __future__ import annotations

import re
from datetime import date, datetime

from jobspy.model import (
    Compensation,
    CompensationInterval,
    Country,
    JobType,
    Location,
)

# Level uses ISO 3166 codes, JobSpy's Country enum uses "uk" for Great Britain
_country_code_aliases = {"UK": "GB"}

_salary_intervals = {
    "year": CompensationInterval.YEARLY,
    "month": CompensationInterval.MONTHLY,
    "week": CompensationInterval.WEEKLY,
    "day": CompensationInterval.DAILY,
    "hour": CompensationInterval.HOURLY,
}


def text_of(element, tag: str) -> str | None:
    value = element.findtext(tag)
    if value is None:
        return None
    value = value.strip()
    return value or None


def strip_tags(html: str | None) -> str | None:
    if not html:
        return html
    return re.sub(r"<[^>]+>", " ", html)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def country_code_from_string(value: str | None) -> str | None:
    """Maps "usa", "United Kingdom", "gb"... to an ISO 3166 alpha-2 code."""
    if not value:
        return None
    value = value.strip()
    if len(value) == 2 and value.isalpha():
        return _country_code_aliases.get(value.upper(), value.upper())
    try:
        country = Country.from_string(value)
    except ValueError:
        return None
    code = country.value[1].split(":")[-1].upper()
    if len(code) != 2:
        return None
    return _country_code_aliases.get(code, code)


def parse_location(city: str | None, country_code: str | None) -> Location:
    # Level puts the country name in <city> when a job is country-wide
    if city and country_code_from_string(city) == country_code:
        city = None
    return Location(city=city, country=country_code)


def matches_location(
    location: str | None, city: str | None, country_code: str | None
) -> bool:
    if not location:
        return True
    wanted = location.split(",")[0].strip().lower()
    if not wanted:
        return True
    if city:
        city_lower = city.lower()
        # short inputs ("us", "ca") are codes, never substrings of a city name
        if wanted == city_lower or (len(wanted) > 3 and wanted in city_lower):
            return True
    wanted_code = country_code_from_string(wanted)
    return bool(wanted_code and country_code and wanted_code == country_code)


def matches_search_term(search_term: str | None, *texts: str | None) -> bool:
    if not search_term:
        return True
    haystack = " ".join(text for text in texts if text).lower()
    terms = re.findall(r"\w[\w+#.-]*", search_term.lower())
    return all(term in haystack for term in terms)


def parse_job_type(value: str | None) -> list[JobType] | None:
    if not value:
        return None
    normalized = re.sub(r"[\s_-]", "", value.lower())
    for job_type in JobType:
        if any(normalized.startswith(alias) for alias in job_type.value):
            return [job_type]
    if normalized.startswith("intern"):
        return [JobType.INTERNSHIP]
    if normalized.startswith(("regularfulltime", "permanent")):
        return [JobType.FULL_TIME]
    if normalized.startswith(("fixedterm", "temp")):
        return [JobType.TEMPORARY]
    return None


def parse_compensation(job) -> Compensation | None:
    min_amount = text_of(job, "salary_min")
    max_amount = text_of(job, "salary_max")
    if not min_amount and not max_amount:
        return None
    try:
        return Compensation(
            interval=_salary_intervals.get(text_of(job, "salary_frequency") or ""),
            min_amount=float(min_amount) if min_amount else None,
            max_amount=float(max_amount) if max_amount else None,
            currency=text_of(job, "salary_currency") or "USD",
        )
    except ValueError:
        return None
