from datetime import datetime
from urllib.parse import urljoin

from jobspy.model import Location


def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except Exception:
        return None


def parse_location(location_text):
    if not location_text:
        return None
    return Location(city=location_text)


def parse_job_url(url):
    if not url:
        return None
    return urljoin("https://remoteok.com", url)


def matches_search_term(job, search_term):
    if not search_term:
        return True

    tags = job.get("tags") or []
    text = " ".join(
        [
            job.get("position") or "",
            job.get("company") or "",
            job.get("description") or "",
            " ".join(tags),
        ]
    ).lower()

    return search_term.lower() in text