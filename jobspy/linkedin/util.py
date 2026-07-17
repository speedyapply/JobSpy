import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from jobspy.model import JobType, Location
from jobspy.util import get_enum_from_job_type

_RELATIVE_RE = re.compile(
    r"^\s*(?:just\s+now|today|yesterday|(\d+)\s*(minute|minutes|min|hour|hours|hr|hrs|day|days|week|weeks|month|months|year|years)\s+ago)\s*$",
    re.IGNORECASE,
)


def job_type_code(job_type_enum: JobType) -> str:
    return {
        JobType.FULL_TIME: "F",
        JobType.PART_TIME: "P",
        JobType.INTERNSHIP: "I",
        JobType.CONTRACT: "C",
        JobType.TEMPORARY: "T",
    }.get(job_type_enum, "")


def parse_job_type(soup_job_type: BeautifulSoup) -> list[JobType] | None:
    """
    Gets the job type from job page
    :param soup_job_type:
    :return: JobType
    """
    h3_tag = soup_job_type.find(
        "h3",
        class_="description__job-criteria-subheader",
        string=lambda text: "Employment type" in text,
    )
    employment_type = None
    if h3_tag:
        employment_type_span = h3_tag.find_next_sibling(
            "span",
            class_="description__job-criteria-text description__job-criteria-text--criteria",
        )
        if employment_type_span:
            employment_type = employment_type_span.get_text(strip=True)
            employment_type = employment_type.lower()
            employment_type = employment_type.replace("-", "")

    return [get_enum_from_job_type(employment_type)] if employment_type else []


def parse_job_level(soup_job_level: BeautifulSoup) -> str | None:
    """
    Gets the job level from job page
    :param soup_job_level:
    :return: str
    """
    h3_tag = soup_job_level.find(
        "h3",
        class_="description__job-criteria-subheader",
        string=lambda text: "Seniority level" in text,
    )
    job_level = None
    if h3_tag:
        job_level_span = h3_tag.find_next_sibling(
            "span",
            class_="description__job-criteria-text description__job-criteria-text--criteria",
        )
        if job_level_span:
            job_level = job_level_span.get_text(strip=True)

    return job_level


def parse_company_industry(soup_industry: BeautifulSoup) -> str | None:
    """
    Gets the company industry from job page
    :param soup_industry:
    :return: str
    """
    h3_tag = soup_industry.find(
        "h3",
        class_="description__job-criteria-subheader",
        string=lambda text: "Industries" in text,
    )
    industry = None
    if h3_tag:
        industry_span = h3_tag.find_next_sibling(
            "span",
            class_="description__job-criteria-text description__job-criteria-text--criteria",
        )
        if industry_span:
            industry = industry_span.get_text(strip=True)

    return industry


def parse_job_datetime(time_tag) -> tuple[datetime | None, str | None]:
    """Parse LinkedIn <time> into a datetime + provenance.

    Prefers relative text ("3 hours ago") for hour-level precision; falls back
    to the datetime="YYYY-MM-DD" attribute (day precision only).
    """
    if time_tag is None:
        return None, None

    now = datetime.now(timezone.utc)
    text = time_tag.get_text(strip=True) or ""
    match = _RELATIVE_RE.match(text)
    if match:
        lower = text.lower().strip()
        if lower in ("just now", "today"):
            return now, "linkedin_relative_text"
        if lower == "yesterday":
            return now - timedelta(days=1), "linkedin_relative_text"

        amount = int(match.group(1))
        unit = match.group(2).lower()
        if unit.startswith("min"):
            delta = timedelta(minutes=amount)
        elif unit.startswith("hour") or unit.startswith("hr"):
            delta = timedelta(hours=amount)
        elif unit.startswith("day"):
            delta = timedelta(days=amount)
        elif unit.startswith("week"):
            delta = timedelta(weeks=amount)
        elif unit.startswith("month"):
            delta = timedelta(days=30 * amount)
        else:
            delta = timedelta(days=365 * amount)
        return now - delta, "linkedin_relative_text"

    datetime_attr = time_tag.get("datetime")
    if datetime_attr:
        try:
            # Date-only attribute → noon UTC so "yesterday" doesn't look >24h
            # the moment local midnight rolls over.
            parsed = datetime.strptime(datetime_attr, "%Y-%m-%d").replace(
                hour=12, tzinfo=timezone.utc
            )
            return parsed, "linkedin_datetime_attr"
        except ValueError:
            pass

    return None, None


def is_job_remote(title: dict, description: str, location: Location) -> bool:
    """
    Searches the title, location, and description to check if job is remote
    """
    remote_keywords = ["remote", "work from home", "wfh"]
    location = location.display_location()
    full_string = f"{title} {description} {location}".lower()
    is_remote = any(keyword in full_string for keyword in remote_keywords)
    return is_remote
