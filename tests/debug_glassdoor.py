
import pytest
from jobspy import scrape_jobs
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_glassdoor_debug():
    """
    Runs a single page scrape on Glassdoor with verbose logging enabled
    to trigger the debug output we just added.
    """
    print("\n--- DEBUGGING GLASSDOOR ---")
    try:
        jobs = scrape_jobs(
            site_name=["glassdoor"],
            search_term="software engineer",
            location="San Francisco, CA",
            results_wanted=3,
            country_indeed="usa",
            verbose=2, # Triggers the debug logs
            hours_old=72
        )
        print(f"Jobs found: {len(jobs)}")
    except Exception as e:
        print(f"Scrape failed: {e}")
