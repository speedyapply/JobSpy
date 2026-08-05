from __future__ import annotations

import json
import re
from datetime import datetime

from bs4 import BeautifulSoup

from jobspy.model import Compensation, CompensationInterval, Location, Country


def extract_next_data(html: str) -> dict | None:
    """
    Extract and parse the __NEXT_DATA__ script tag from Wellfound HTML.
    This contains the Apollo cache with all structured job data.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if script_tag and script_tag.string:
            return json.loads(script_tag.string)
    except (json.JSONDecodeError, AttributeError):
        pass
    return None


def get_apollo_state(next_data: dict) -> dict | None:
    """
    Navigate the __NEXT_DATA__ structure to get the Apollo state cache.
    """
    try:
        return next_data["props"]["pageProps"]["apolloState"]["data"]
    except (KeyError, TypeError):
        return None


def resolve_apollo_ref(apollo_data: dict, ref: dict | None) -> dict | None:
    """
    Resolve an Apollo cache reference like {'__ref': 'Startup:12345'}
    to the actual entity data from the cache.
    """
    if not ref or not isinstance(ref, dict):
        return None
    ref_key = ref.get("__ref")
    if ref_key and ref_key in apollo_data:
        return apollo_data[ref_key]
    return None


def parse_compensation_string(comp_str: str) -> Compensation | None:
    """
    Parse Wellfound compensation strings like:
      - "$60k – $70k • 1.0% – 2.0%"
      - "$120k – $180k • No equity"
      - "$45k – $65k"
      - "Equity Only • 0.5% – 1.0%"
    Returns a Compensation object or None.
    """
    if not comp_str:
        return None

    # Extract salary range: $60k – $70k or $120,000 – $180,000
    salary_pattern = r"\$(\d+(?:,\d+)?(?:\.\d+)?)\s*([kK])?\s*[–\-—]\s*\$(\d+(?:,\d+)?(?:\.\d+)?)\s*([kK])?"
    match = re.search(salary_pattern, comp_str)

    if not match:
        return None

    min_val = float(match.group(1).replace(",", ""))
    min_suffix = match.group(2)
    max_val = float(match.group(3).replace(",", ""))
    max_suffix = match.group(4)

    if min_suffix and min_suffix.lower() == "k":
        min_val *= 1000
    if max_suffix and max_suffix.lower() == "k":
        max_val *= 1000

    return Compensation(
        interval=CompensationInterval.YEARLY,
        min_amount=min_val,
        max_amount=max_val,
        currency="USD",
    )


def parse_location_names(
    location_names: list[str] | None,
    is_remote: bool = False,
) -> Location | None:
    """
    Parse Wellfound locationNames list into a Location object.
    Uses the first location name as the city.
    """
    if not location_names:
        return Location(country=Country.USA)

    city = location_names[0] if location_names else None

    return Location(city=city)


def slugify(text: str) -> str:
    """
    Convert a text string into a URL-friendly slug.
    e.g., 'San Francisco, CA' -> 'san-francisco-ca'
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def timestamp_to_date(timestamp: int | None):
    """
    Convert a Unix timestamp to a date object.
    """
    if not timestamp:
        return None
    try:
        return datetime.fromtimestamp(timestamp).date()
    except (OSError, ValueError, OverflowError):
        return None