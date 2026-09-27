"""Debug entry point: scrape jobs and parse the returned DataFrame rows into JobPost models."""

import csv
import json
import logging
import os

import pandas as pd

from jobspy import scrape_jobs
from jobspy.model import (
    Compensation,
    CompensationInterval,
    Country,
    JobPost,
    JobType,
    Location,
)

logger = logging.getLogger("debug_run")


def _clean(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _split(value) -> list[str] | None:
    value = _clean(value)
    if not value:
        return None
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _job_types(value) -> list[JobType] | None:
    parts = _split(value)
    if not parts:
        return None
    lookup = {job_type.value[0]: job_type for job_type in JobType}
    types = [lookup[part] for part in parts if part in lookup]
    return types or None


def _location(value) -> Location | None:
    parts = _split(value)
    if not parts:
        return None
    try:
        country = Country.from_string(parts[-1])
        parts = parts[:-1]
    except ValueError:
        country = None
    city = parts[0] if parts else None
    state = parts[1] if len(parts) > 1 else None
    if country is None and len(parts) > 2:
        country = parts[-1]
    return Location(city=city, state=state, country=country)


def _compensation(row: dict) -> Compensation | None:
    min_amount = _clean(row.get("min_amount"))
    max_amount = _clean(row.get("max_amount"))
    if min_amount is None and max_amount is None:
        return None
    interval = _clean(row.get("interval"))
    return Compensation(
        interval=CompensationInterval(interval) if interval else None,
        min_amount=min_amount,
        max_amount=max_amount,
        currency=_clean(row.get("currency")) or "USD",
    )


def row_to_jobpost(row: dict) -> JobPost | None:
    try:
        data = {
            field: _clean(row.get(field))
            for field in JobPost.model_fields
            if field in row
        }
        data["company_name"] = _clean(row.get("company"))
        data["job_type"] = _job_types(row.get("job_type"))
        data["emails"] = _split(row.get("emails"))
        data["skills"] = _split(row.get("skills"))
        data["location"] = _location(row.get("location"))
        data["compensation"] = _compensation(row)
        date_posted = data.get("date_posted")
        if isinstance(date_posted, pd.Timestamp):
            data["date_posted"] = date_posted.date()
        for int_field in ("company_reviews_count", "vacancy_count"):
            if data.get(int_field) is not None:
                data[int_field] = int(data[int_field])
        return JobPost(**data)
    except Exception:
        logger.exception("Failed to parse row: %s", row.get("job_url"))
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # e.g. http://scrapeops:<API_KEY>@residential-proxy.scrapeops.io:8181
    proxy = os.environ.get("SCRAPEOPS_PROXY")

    df = scrape_jobs(
        site_name=["linkedin"],
        search_term="Software Engineer, Information technology, AI, ML, Business analyst, Project management, Cloud, DevOps, Networking",
        location="Sri Lanka",
        hours_old=2,
        results_wanted=50,
        linkedin_fetch_description=True,
        proxies=[proxy] if proxy else None,
    )
    print(f"Scraped {len(df)} rows")

    posts = [post for post in (row_to_jobpost(r) for r in df.to_dict("records")) if post]
    print(f"Parsed {len(posts)} JobPost models")

    df.to_csv("jobs.csv", quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False)
    print(f"Saved {len(df)} rows to jobs.csv")

    with open("jobs.json", "w", encoding="utf-8") as f:
        json.dump(
            [post.model_dump(mode="json") for post in posts],
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Saved {len(posts)} JobPost models to jobs.json")
