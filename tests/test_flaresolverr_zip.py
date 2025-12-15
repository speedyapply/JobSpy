
import requests
import json
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("FlaresolverrTest")

def test_ziprecruiter_bypass():
    """
    Tests if Flaresolverr can successfully retrieve a ZipRecruiter search page
    without getting blocked.
    """
    flaresolverr_url = os.getenv("FLARESOLVERR_URL", "http://localhost:8191/v1")
    target_url = "https://www.ziprecruiter.com/jobs-search?search=software+engineer&location=San+Francisco%2C+CA"
    
    payload = {
        "cmd": "request.get",
        "url": target_url,
        "maxTimeout": 60000
    }
    
    log.info(f"Sending request to Flaresolverr: {flaresolverr_url}")
    log.info(f"Target URL: {target_url}")
    
    import time
    max_retries = 15
    for i in range(max_retries):
        try:
            log.info(f"Attempt {i+1}/{max_retries}: Sending request to Flaresolverr...")
            response = requests.post(flaresolverr_url, json=payload, headers={"Content-Type": "application/json"})
            response.raise_for_status()
            break
        except requests.exceptions.ConnectionError:
            log.warning("Connection refused. Flaresolverr might be starting up. Waiting 2s...")
            time.sleep(2)
        except Exception as e:
            log.error(f"Request failed with unhandled socket error: {e}")
            return # Don't retry on other errors
            
    else:
        log.error("Timed out waiting for Flaresolverr.")
        return

    data = response.json()
    if data.get("status") == "ok":
        solution = data.get("solution", {})
        response_text = solution.get("response", "")
        
        log.info("Flaresolverr returned 'ok' status.")
        log.info(f"Response length: {len(response_text)}")
        
        # Save response to file for inspection
        with open("ziprecruiter_poc.html", "w") as f:
            f.write(response_text)
            
        # Basic Verification
        if "Just a moment..." in response_text:
                log.error("FAIL: Still seeing Cloudflare challenge page.")
        elif "software engineer" in response_text.lower():
                log.info("SUCCESS: Found 'software engineer' in response.")
                print("SUCCESS: Retrieved content via Flaresolverr")
        else:
                log.warning("WARNING: Did not find expected content, but also didn't see explicit challenge. Check ziprecruiter_poc.html")
                
    else:
        log.error(f"Flaresolverr failed: {data.get('message', 'Unknown error')}")

if __name__ == "__main__":
    test_ziprecruiter_bypass()
