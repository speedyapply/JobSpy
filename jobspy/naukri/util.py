from __future__ import annotations

from bs4 import BeautifulSoup
from jobspy.model import JobType, Location
from jobspy.util import get_enum_from_job_type


def parse_job_type(soup: BeautifulSoup) -> list[JobType] | None:
    """
    Gets the job type from the job page
    """
    job_type_tag = soup.find("span", class_="job-type")
    if job_type_tag:
        job_type_str = job_type_tag.get_text(strip=True).lower().replace("-", "")
        return [get_enum_from_job_type(job_type_str)] if job_type_str else None
    return None


def parse_company_industry(soup: BeautifulSoup) -> str | None:
    """
    Gets the company industry from the job page
    """
    industry_tag = soup.find("span", class_="industry")
    return industry_tag.get_text(strip=True) if industry_tag else None


def is_job_remote(title: str, description: str, location: Location) -> bool:
    """
    Searches the title, description, and location to check if the job is remote
    """
    remote_keywords = ["remote", "work from home", "wfh"]
    location_str = location.display_location()
    full_string = f"{title} {description} {location_str}".lower()
    return any(keyword in full_string for keyword in remote_keywords)