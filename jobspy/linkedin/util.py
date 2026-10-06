import re

from bs4 import BeautifulSoup

from jobspy.linkedin.constant import remote_keywords
from jobspy.model import Country, Location


def criteria(soup: BeautifulSoup, heading: str) -> str | None:
    """
    The value under a heading of the job page's criteria list ("Seniority level", "Employment type", ...)
    """
    h3_tag = soup.find(
        "h3",
        class_="description__job-criteria-subheader",
        string=lambda text: text and heading in text,
    )
    span = (
        h3_tag.find_next_sibling("span", class_="description__job-criteria-text")
        if h3_tag
        else None
    )
    return span.get_text(strip=True) if span else None


def is_job_remote(title: str, location: Location) -> bool:
    """
    A remote keyword in the title or location
    """
    text = f"{title} {location.display_location()}".lower()
    return any(keyword in text for keyword in remote_keywords)


def parse_location(text: str) -> Location:
    """
    "City, State, Country", "City, ST" (US jobs), "City, Country", or one name: a country or an area
    """
    parts = text.split(", ")
    if len(parts) == 3:
        city, state, country = parts
        return Location(city=city, state=state, country=country)
    if len(parts) == 2:
        city, last = parts
        if re.fullmatch(r"[A-Z]{2}", last):
            return Location(city=city, state=last, country=Country.USA)
        return Location(city=city, country=last)
    try:
        Country.from_string(text)
        return Location(country=text)
    except ValueError:
        return Location(city=text)
