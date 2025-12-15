from jobspy import scrape_jobs
import logging
import sys

# Enable verbose logging
logging.basicConfig(level=logging.INFO)

import os

def test_ziprecruiter():
    print("Testing ZipRecruiter...")
    jobs = scrape_jobs(
        site_name=["zip_recruiter"],
        search_term="software engineer",
        location="San Francisco, CA",
        results_wanted=5,
        flaresolverr_url=os.getenv("FLARESOLVERR_URL", "http://localhost:8191"), # User to confirm URL
        verbose=2
    )
    print(f"Found {len(jobs)} ZipRecruiter jobs")
    if not jobs.empty:
        print(jobs.iloc[0])

def test_glassdoor():
    print("Testing Glassdoor...")
    jobs = scrape_jobs(
        site_name=["glassdoor"],
        search_term="software engineer",
        location="San Francisco, CA",
        results_wanted=5,
        flaresolverr_url=os.getenv("FLARESOLVERR_URL", "http://localhost:8191"),
        verbose=2
    )
    print(f"Found {len(jobs)} Glassdoor jobs")
    if not jobs.empty:
        print(jobs.iloc[0])

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "glassdoor":
        test_glassdoor()
    elif len(sys.argv) > 1 and sys.argv[1] == "ziprecruiter":
        test_ziprecruiter()
    else:
        test_ziprecruiter()
        test_glassdoor()
