from __future__ import annotations

import re
from datetime import timedelta
from typing import List

from bs4 import BeautifulSoup
from bs4.element import Tag

from jobspy.model import Compensation, CompensationInterval


def find_job_cards(soup: BeautifulSoup) -> List[Tag]:
    cards = soup.find_all(
        "div",
        class_=lambda c: c and "individual_internship" in c,
    )
    if cards:
        return cards

    return soup.find_all("div", attrs={"internshipid": True})


def parse_location(card: Tag) -> tuple[str | None, bool]:
    text = card.get_text(" ", strip=True)
    lower_text = text.lower()

    is_remote = "work from home" in lower_text

    if is_remote:
        return "Work from home", True

    prefix = text
    rupee_idx = text.find("₹")
    if rupee_idx != -1:
        prefix = text[:rupee_idx]

    matches = re.findall(r"\b([A-Z][a-zA-Z]+(?:,\s*[A-Z][a-zA-Z]+)*)\b", prefix)
    location_text = matches[-1] if matches else None

    return location_text, is_remote


def parse_posted_ago(card: Tag) -> timedelta | None:
    text = card.get_text(" ", strip=True).lower()

    if "today" in text or "just now" in text:
        return timedelta(hours=0)
    if "yesterday" in text:
        return timedelta(days=1)

    match = re.search(r"(\d+)\s+(day|days|week|weeks|month|months) ago", text)
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit.startswith("day"):
        return timedelta(days=value)
    if unit.startswith("week"):
        return timedelta(weeks=value)
    if unit.startswith("month"):
        # Rough approximation
        return timedelta(days=30 * value)

    return None


def parse_stipend(card: Tag) -> Compensation | None:
    text = card.get_text(" ", strip=True)
    stipend_match = re.search(
        r"₹\s*([0-9,]+)\s*-\s*([0-9,]+)\s*/month", text,
        flags=re.IGNORECASE,
    )
    if not stipend_match:
        # Try single-value stipend like "₹ 10,000 /month"
        single_match = re.search(r"₹\s*([0-9,]+)\s*/month", text, flags=re.IGNORECASE)
        if not single_match:
            return None
        amount = int(single_match.group(1).replace(",", ""))
        return Compensation(
            interval=CompensationInterval.MONTHLY,
            min_amount=amount,
            max_amount=amount,
            currency="INR",
        )

    min_raw, max_raw = stipend_match.groups()
    min_amount = int(min_raw.replace(",", ""))
    max_amount = int(max_raw.replace(",", ""))

    return Compensation(
        interval=CompensationInterval.MONTHLY,
        min_amount=min_amount,
        max_amount=max_amount,
        currency="INR",
    )
