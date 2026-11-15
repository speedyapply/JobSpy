import re

from jobspy.model import CompensationInterval

jobs_per_page = 10
max_results = 1000
empty_page = "<!DOCTYPE html>\n\n<!---->"

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

currencies = {"$": "USD", "CA$": "CAD", "£": "GBP", "€": "EUR", "₹": "INR"}

pay_intervals = {
    "/hr": CompensationInterval.HOURLY,
    "/mo": CompensationInterval.MONTHLY,
    "/yr": CompensationInterval.YEARLY,
}

remote_keywords = ["remote", "work from home", "wfh"]

lower_limit, upper_limit = 1000, 700000
hourly_threshold, monthly_threshold = 350, 30000
# "$80k - $100k" or "$80,000 to $100,000"; not "$5-10M" or "$20 - $30 million"
salary_range = re.compile(
    r"\$(\d+(?:,\d+)?(?:\.\d+)?)([kK]?)\s*(?:[-—–]|to)\s*(?:\$)?(\d+(?:,\d+)?(?:\.\d+)?)([kK]?)"
    r"(?![\d.,]*\d|\s*(?:[mMbB]\b|[mb]illion\b|bn\b))"
)
