from datetime import date, datetime, timedelta

from jobspy.model import Location


def parse_date_posted(text: str) -> date | None:
    """Parse JobStreet relative date strings like '2 hari yang lalu' or 'Hari Ini'."""
    if not text:
        return None

    text_clean = text.split("•")[0].strip()
    text_lower = text_clean.lower()
    today = datetime.today().date()

    if "hari ini" in text_lower:
        return today
    if "hari" in text_lower or "day" in text_lower:
        try:
            days = int("".join(filter(str.isdigit, text_lower)))
            return today - timedelta(days=days)
        except ValueError:
            return None
    if (
        "jam yang lalu" in text_lower
        or "hours ago" in text_lower
        or "hour" in text_lower
    ):
        try:
            int("".join(filter(str.isdigit, text_lower)))
            return today
        except ValueError:
            return today
    if (
        "menit yang lalu" in text_lower
        or "minutes ago" in text_lower
        or "minute" in text_lower
    ):
        return today

    return None


def parse_location(text: str) -> Location:
    """Parse JobStreet location strings into Location model."""
    if not text:
        return Location(country="Indonesia")

    parts = [p.strip() for p in text.split(",")]

    if len(parts) == 1:
        return Location(country="Indonesia", city=parts[0])
    elif len(parts) == 2:
        return Location(country="Indonesia", city=parts[0], state=parts[1])
    else:
        return Location(country="Indonesia", city=parts[0], state=parts[1])
