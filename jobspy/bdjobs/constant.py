#constant.py
# Headers for BDJobs requests
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Referer": "https://jobs.bdjobs.com/",
    "Cache-Control": "max-age=0",
}

# Search parameters that work best for BDJobs
search_params = {
    "hidJobSearch": "jobsearch",
}

# Selectors for job listings
job_selectors = [
    "div.job-item",  # Catches both normal and premium job cards, as well as other types
    "div.sout-jobs-wrapper", # Catches job listings in the main search results page
    "div.norm-jobs-wrapper", # Catches normal job listings
    "div.featured-wrap",     # Catches featured job listings
]

# Date formats used by BDJobs
date_formats = [
    "%d %b %Y",
    "%d-%b-%Y",
    "%d %B %Y",
    "%B %d, %Y",
    "%d/%m/%Y",
]