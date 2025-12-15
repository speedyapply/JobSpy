
import pytest
from jobspy import scrape_jobs
from jobspy.indeed import Indeed
from jobspy.linkedin import LinkedIn
from jobspy.glassdoor import Glassdoor
from jobspy.google import Google
from jobspy.ziprecruiter import ZipRecruiter

def test_scraper_imports():
    """Test that all scraper classes can be imported and instantiated."""
    # Just basic instantiation to check for syntax errors or missing dependencies
    indeed = Indeed()
    assert indeed is not None
    
    linkedin = LinkedIn()
    assert linkedin is not None
    
    # Google scraper doesn't take user_agent in current init logic shown in logs, 
    # but let's check basic init
    google = Google()
    assert google is not None
    
    zip_recruiter = ZipRecruiter()
    assert zip_recruiter is not None
    
    glassdoor = Glassdoor()
    assert glassdoor is not None

def test_scrape_jobs_signature():
    """Verify scrape_jobs accepts the new rate limiting arguments."""
    # We don't want to actually scrape (it takes time/network), 
    # but we can check if the function accepts the args without erroring on signature
    try:
        # Calling with invalid site to trigger early return or minimal execution
        scrape_jobs(
            site_name=[], 
            search_term="test", 
            rate_delay_min=1, 
            rate_delay_max=2
        )
    except Exception as e:
        pytest.fail(f"scrape_jobs raised exception with rate limit args: {e}")
