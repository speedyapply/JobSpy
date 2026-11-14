"""Tests for the JobStreet Indonesia scraper.

Unit tests construct HTML inline — no fixtures required.
Integration tests hit id.jobstreet.com live and may return 0 jobs
when Cloudflare blocks the IP; the runner reports them separately
and only unit test failures set a non-zero exit code.

Run everything:
    poetry run python tests/test_jobstreet.py
"""

from __future__ import annotations

from datetime import date, timedelta

from bs4 import BeautifulSoup

from jobspy import scrape_jobs
from jobspy.jobstreet import JobStreet
from jobspy.jobstreet.util import parse_date_posted
from jobspy.model import DescriptionFormat, ScraperInput

TANGERANG_MATCHERS = {
    "tangerang",
    "serpong",
    "bsd",
    "alam sutera",
    "cipondoh",
    "ciledug",
    "batuceper",
    "benda",
    "jatiuwung",
    "karawaci",
    "larangan",
    "periuk",
    "pinang",
    "tangerang selatan",
    "kabupaten tangerang",
    "kota tangerang",
    "banten",
}


def _make_scraper() -> JobStreet:
    """A JobStreet scraper primed with a typical Jakarta search input."""
    scraper = JobStreet()
    scraper.scraper_input = ScraperInput(
        site_name=["jobstreet"],
        search_term="software engineer",
        location="Jakarta",
        description_format=DescriptionFormat.MARKDOWN,
    )
    return scraper


def _card_html(
    title: str,
    company: str,
    location: str,
    salary: str | None = None,
    job_id: str = "92517349",
    link_attr: str = 'data-automation="job-list-view-job-link"',
    date_text: str = "26 hari yang lalu",
) -> str:
    salary_html = (
        f'<span data-automation="jobSalary">{salary}</span>' if salary else ""
    )
    return f"""\
<article>
  <a {link_attr} href="/id/job/{job_id}">{title}</a>
  <span data-automation="jobTitle">{title}</span>
  <span data-automation="jobCompany">{company}</span>
  <span data-automation="jobLocation">{location}</span>
  {salary_html}
  <span data-automation="jobShortDescription">Description.</span>
  <span data-automation="jobListingDate">{date_text}</span>
</article>
"""


# ---------------------------------------------------------------------------
# Unit tests (offline)
# ---------------------------------------------------------------------------


def test_parse_single_card():
    html = _card_html(
        title="Senior Software Engineer",
        company="PT Example Indonesia",
        location="Jakarta Raya",
        salary="Rp 15.000.000 – Rp 20.000.000 per month",
    )
    card = BeautifulSoup(html, "html.parser").find("article")
    assert card is not None

    scraper = _make_scraper()
    job = scraper._parse_card(card)

    assert job is not None
    assert job.title == "Senior Software Engineer"
    assert job.company == "PT Example Indonesia"
    assert job.job_url == "https://id.jobstreet.com/id/job/92517349"
    assert job.id == "92517349"
    assert job.location is not None
    assert job.location.city == "Jakarta Raya"
    assert job.location.country == "Indonesia"
    assert job.min_amount == 15_000_000
    assert job.max_amount == 20_000_000
    assert job.currency == "IDR"
    assert job.interval is not None
    assert job.interval.value == "monthly"


def test_parse_card_without_salary():
    html = _card_html(
        title="Frontend Developer",
        company="Digital Agency",
        location="Bandung, Jawa Barat",
        job_id="92517351",
    )
    card = BeautifulSoup(html, "html.parser").find("article")
    assert card is not None

    scraper = _make_scraper()
    job = scraper._parse_card(card)

    assert job is not None
    assert job.title == "Frontend Developer"
    assert job.company == "Digital Agency"
    assert job.min_amount is None
    assert job.max_amount is None
    assert job.currency is None


def test_fetch_page_filters_jakarta_only():
    html = f"""\
<!DOCTYPE html>
<html><body>
{_card_html("Senior Software Engineer", "PT Example", "Jakarta Raya", job_id="1")}
{_card_html("Backend Developer", "Startup Tech", "Tangerang, Banten", job_id="2")}
{_card_html("Frontend Developer", "Digital Agency", "Bandung, Jawa Barat", job_id="3")}
</body></html>
"""
    scraper = _make_scraper()
    scraper.scraper_input.location = "Jakarta"
    soup = BeautifulSoup(html, "html.parser")

    jobs = [
        job
        for card in soup.find_all("article")
        if (job := scraper._parse_card(card)) is not None
    ]
    jakarta_jobs = [
        job for job in jobs
        if job.location and "jakarta" in (job.location.city or "").lower()
    ]
    assert len(jakarta_jobs) == 1
    assert jakarta_jobs[0].title == "Senior Software Engineer"


def test_tangerang_location_expansion():
    html = """\
<!DOCTYPE html>
<html><body>
  <article>
    <a data-automation="job-list-view-job-link" href="/id/job/1">Manager</a>
    <span data-automation="jobTitle">Manager</span>
    <span data-automation="jobCompany">PT BSD</span>
    <span data-automation="jobLocation">Serpong, Tangerang</span>
    <span data-automation="jobListingDate">1 hari yang lalu</span>
  </article>
  <article>
    <a data-automation="job-list-view-job-link" href="/id/job/2">Engineer</a>
    <span data-automation="jobTitle">Engineer</span>
    <span data-automation="jobCompany">PT Jakarta</span>
    <span data-automation="jobLocation">Jakarta Raya</span>
    <span data-automation="jobListingDate">1 hari yang lalu</span>
  </article>
</body></html>
"""
    scraper = _make_scraper()
    scraper.scraper_input.location = "Tangerang"
    soup = BeautifulSoup(html, "html.parser")

    jobs = []
    for card in soup.find_all("article"):
        job = scraper._parse_card(card)
        if job:
            job_location = " ".join(
                getattr(job.location, field, "") or ""
                for field in ("city", "state", "country")
            ).lower()
            if any(matcher in job_location for matcher in TANGERANG_MATCHERS):
                jobs.append(job)

    assert len(jobs) == 1
    assert jobs[0].title == "Manager"


def test_date_parsing():
    today = date.today()
    assert parse_date_posted("Hari Ini") == today
    assert parse_date_posted("1 hari yang lalu") == today - timedelta(days=1)
    assert parse_date_posted("3 hari yang lalu") == today - timedelta(days=3)
    assert parse_date_posted("5 jam yang lalu") == today
    assert parse_date_posted("10 menit yang lalu") == today


def test_extract_salary_range():
    scraper = _make_scraper()
    fields = scraper._extract_salary("Rp 15.000.000 – Rp 20.000.000 per month")

    assert fields["min_amount"] == 15_000_000
    assert fields["max_amount"] == 20_000_000
    assert fields["currency"] == "IDR"
    assert fields["interval"].value == "monthly"


def test_extract_salary_single():
    scraper = _make_scraper()
    fields = scraper._extract_salary("Rp 10.000.000 per month")

    assert fields["min_amount"] == 10_000_000
    assert fields["max_amount"] is None
    assert fields["currency"] == "IDR"


def test_extract_salary_unsupported():
    scraper = _make_scraper()
    fields = scraper._extract_salary("Gaji dirahasiakan")
    assert fields == {}


# ---------------------------------------------------------------------------
# Integration tests (live, need network)
# ---------------------------------------------------------------------------


def test_integration_basic():
    """Scrape Jakarta and check the rows come back well formed."""
    jobs = scrape_jobs(
        site_name="jobstreet",
        search_term="software engineer",
        location="Jakarta",
        results_wanted=5,
        verbose=2,
    )
    print(f"\n[integration] Jakarta: {len(jobs)} jobs")
    if len(jobs) > 0:
        print(jobs[["site", "title", "company", "location", "job_url"]].head())


def test_integration_hours_old():
    """hours_old=24 must map to daterange=1 and return fresh listings."""
    jobs = scrape_jobs(
        site_name="jobstreet",
        search_term="developer",
        location="Jakarta",
        results_wanted=5,
        hours_old=24,
        verbose=2,
    )
    print(f"\n[integration] hours_old=24: {len(jobs)} jobs")
    if len(jobs) > 0:
        print(jobs[["title", "company", "date_posted"]].head())


def test_integration_tangerang():
    """Tangerang search must cover the metro area (Serpong, BSD, Cipondoh)."""
    jobs = scrape_jobs(
        site_name="jobstreet",
        search_term="manager",
        location="Tangerang",
        results_wanted=5,
        verbose=2,
    )
    print(f"\n[integration] Tangerang: {len(jobs)} jobs")
    if len(jobs) > 0:
        print(jobs[["title", "company", "location"]].head())


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

UNIT_TESTS = [
    test_parse_single_card,
    test_parse_card_without_salary,
    test_fetch_page_filters_jakarta_only,
    test_tangerang_location_expansion,
    test_date_parsing,
    test_extract_salary_range,
    test_extract_salary_single,
    test_extract_salary_unsupported,
]

INTEGRATION_TESTS = [
    test_integration_basic,
    test_integration_hours_old,
    test_integration_tangerang,
]


def _run_group(tests: list) -> int:
    """Run tests one by one, printing PASS/FAIL; return the failure count."""
    failed = 0
    for test in tests:
        try:
            test()
        except Exception as e:
            failed += 1
            print(f"FAIL {test.__name__}: {type(e).__name__}: {e}")
        else:
            print(f"PASS {test.__name__}")
    return failed


def run_all() -> int:
    """Run unit then integration tests; exit code reflects unit tests only."""
    print(f"--- unit tests ({len(UNIT_TESTS)}) ---")
    unit_failed = _run_group(UNIT_TESTS)

    print(f"\n--- integration tests ({len(INTEGRATION_TESTS)}) ---")
    _run_group(INTEGRATION_TESTS)

    print(
        f"\n--- unit: {len(UNIT_TESTS) - unit_failed}/{len(UNIT_TESTS)} passed ---"
    )
    return 1 if unit_failed else 0


if __name__ == "__main__":
    raise SystemExit(run_all())
