
import logging
import os
from jobspy import scrape_jobs

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("IntegrationTest")

def test_ziprecruiter_integration():
    flaresolverr_url = os.getenv("FLARESOLVERR_URL")
    if not flaresolverr_url:
        log.error("FLARESOLVERR_URL env var not set")
        return

    log.info(f"Testing ZipRecruiter with Flaresolverr: {flaresolverr_url}")

    try:
        jobs = scrape_jobs(
            site_name=["zip_recruiter"],
            search_term="software engineer",
            location="San Francisco, CA",
            results_wanted=5,
            country_indeed="usa",
            flaresolverr_url=flaresolverr_url
        )
        
        log.info(f"Jobs found: {len(jobs)}")
        
        if len(jobs) > 0:
            log.info("SUCCESS: Configuration working and jobs parsed.")
            print(jobs.head())
        else:
            log.warning("WARNING: 0 jobs found. Bypass might have worked but parsing failed, or no jobs returned.")
            
    except Exception as e:
        log.error(f"Scrape failed: {e}")

if __name__ == "__main__":
    test_ziprecruiter_integration()
