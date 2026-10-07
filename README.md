<img src="https://github.com/cullenwatson/JobSpy/assets/78247585/ae185b7e-e444-4712-8bb9-fa97f53e896b" width="400">

**JobSpy** is a job scraping library with the goal of aggregating all the jobs from popular job boards with one tool.

## Features

- Scrapes job postings from **LinkedIn**, **Indeed**, **Glassdoor**, **ZipRecruiter**, & other job boards concurrently
- Searches Freehire's public API for open IT roles
- Aggregates the job postings in a dataframe
- Proxies support to bypass blocking

![jobspy](https://github.com/cullenwatson/JobSpy/assets/78247585/ec7ef355-05f6-4fd3-8161-a817e31c5c57)

### Installation

```
pip install -U python-jobspy
```

_Python version >= [3.10](https://www.python.org/downloads/release/python-3100/) required_

### Usage

```python
import csv
from jobspy import scrape_jobs

jobs = scrape_jobs(
    site_name=["indeed", "linkedin", "zip_recruiter", "glassdoor"], # "bayt", "naukri", "bdjobs", "freehire"
    search_term="software engineer",
    location="San Francisco, CA",
    results_wanted=20,
    hours_old=72,
    country_indeed='USA',
    
    # fetch_description=True # for boards whose search results don't include the description (slower)
    # proxies=["208.195.175.46:65095", "208.195.175.45:65095", "localhost"],
)
print(f"Found {len(jobs)} jobs")
print(jobs.head())
jobs.to_csv("jobs.csv", quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False) # to_excel
```

### Output

```
SITE           TITLE                             COMPANY           CITY          STATE  JOB_TYPE  INTERVAL  MIN_AMOUNT  MAX_AMOUNT  JOB_URL                                            DESCRIPTION
indeed         Software Engineer                 AMERICAN SYSTEMS  Arlington     VA     None      yearly    200000      150000      https://www.indeed.com/viewjob?jk=5e409e577046...  THIS POSITION COMES WITH A 10K SIGNING BONUS!...
indeed         Senior Software Engineer          TherapyNotes.com  Philadelphia  PA     fulltime  yearly    135000      110000      https://www.indeed.com/viewjob?jk=da39574a40cb...  About Us TherapyNotes is the national leader i...
linkedin       Software Engineer - Early Career  Lockheed Martin   Sunnyvale     CA     fulltime  yearly    None        None        https://www.linkedin.com/jobs/view/3693012711      Description:By bringing together people that u...
linkedin       Full-Stack Software Engineer      Rain              New York      NY     fulltime  yearly    None        None        https://www.linkedin.com/jobs/view/3696158877      Rain’s mission is to create the fastest and ea...
zip_recruiter Software Engineer - New Grad       ZipRecruiter      Santa Monica  CA     fulltime  yearly    130000      150000      https://www.ziprecruiter.com/jobs/ziprecruiter...  We offer a hybrid work environment. Most US-ba...
zip_recruiter Software Developer                 TEKsystems        Phoenix       AZ     fulltime  hourly    65          75          https://www.ziprecruiter.com/jobs/teksystems-0...  Top Skills' Details• 6 years of Java developme...

```

### Parameters for `scrape_jobs()`

```plaintext
Optional
├── site_name (list|str): 
|    linkedin, zip_recruiter, indeed, glassdoor, google, bayt, bdjobs, naukri, freehire
|    (default is all except google and freehire)
│
├── search_term (str)
|
├── google_search_term (str)
|     search term for google jobs. This is the only param for filtering google jobs.
│
├── location (str)
│
├── distance (int): 
|    in miles, default 50
│
├── job_type (str): 
|    fulltime, parttime, internship, contract
│
├── proxies (list): 
|    in format ['user:pass@host:port', 'localhost']
|    each job board scraper will round robin through the proxies
|
├── is_remote (bool)
│
├── results_wanted (int): 
|    number of job results to retrieve for each site specified in 'site_name'
│
├── easy_apply (bool): 
|    filters for jobs that are hosted on the job board site
|
├── user_agent (str): 
|    override the default user agent which may be outdated
│
├── description_format (str): 
|    markdown, html (Format type of the job descriptions. Default is markdown.)
│
├── offset (int): 
|    starts the search from an offset (e.g. 25 will start the search from the 25th result)
│
├── hours_old (int): 
|    filters jobs by the number of hours since the job was posted 
|    (Glassdoor rounds up to next day.)
│
├── verbose (int) {0, 1, 2}: 
|    Controls the verbosity of the runtime printouts 
|    (0 prints only errors, 1 is errors+warnings, 2 is all logs. Default is 0.)

├── fetch_description (bool): 
|    for boards whose search results don't include the job description: fetches each job's
|    page for the description and other details (e.g. job type). Without it these are empty
|    for those boards. Adds one request per job, so use proxies for larger searches
|    Freehire uses its full-description API endpoint when requested (one request per page).
│
├── linkedin_fetch_description (bool): 
|    deprecated, use fetch_description (still works; removed in 2.0)
│
├── linkedin_company_ids (list[int]): 
|    searches for linkedin jobs with specific company ids
|
├── country_indeed (str): 
|    filters the country on Indeed & Glassdoor (see below for correct spelling)
|
├── enforce_annual_salary (bool): 
|    converts wages to annual salary
|
├── ca_cert (str)
|    path to CA Certificate file for proxies
```

## Supported Countries for Job Searching

### **LinkedIn**

LinkedIn searches globally & uses only the `location` parameter. 

### **ZipRecruiter**

ZipRecruiter searches for jobs in **US/Canada** & uses only the `location` parameter.

### **Indeed / Glassdoor**

Indeed & Glassdoor supports most countries, but the `country_indeed` parameter is required. Additionally, use the `location`
parameter to narrow down the location, e.g. city & state if necessary. 

You can specify the following countries when searching on Indeed (use the exact name, * indicates support for Glassdoor):

|                      |              |            |                |
|----------------------|--------------|------------|----------------|
| Argentina            | Australia*   | Austria*   | Bahrain        |
| Belgium*             | Brazil*      | Canada*    | Chile          |
| China                | Colombia     | Costa Rica | Czech Republic |
| Denmark              | Ecuador      | Egypt      | Finland        |
| France*              | Germany*     | Greece     | Hong Kong*     |
| Hungary              | India*       | Indonesia  | Ireland*       |
| Israel               | Italy*       | Japan      | Kuwait         |
| Luxembourg           | Malaysia     | Mexico*    | Morocco        |
| Netherlands*         | New Zealand* | Nigeria    | Norway         |
| Oman                 | Pakistan     | Panama     | Peru           |
| Philippines          | Poland       | Portugal   | Qatar          |
| Romania              | Saudi Arabia | Singapore* | South Africa   |
| South Korea          | Spain*       | Sweden     | Switzerland*   |
| Taiwan               | Thailand     | Turkey     | Ukraine        |
| United Arab Emirates | UK*          | USA*       | Uruguay        |
| Venezuela            | Vietnam*     |            |                |

### **Bayt**

Bayt searches all countries unless `location` names one it covers, e.g. `"Dubai, UAE"` or `"Saudi Arabia"`.

### **BDJobs**

BDJobs searches Bangladesh. `location` takes a division or district, e.g. `"Dhaka"` or `"Chattogram Division"`.

### **Naukri**

Naukri searches India. `location` takes a city, e.g. `"Pune"`.

### **Freehire**

Freehire searches its global IT-job catalogue through its public API. It is opt-in
because its API is an additional source; specify `site_name="freehire"` to use it.
The adapter requests `is_tech=tech` to exclude non-technical postings; jobs without
a resolved technical classification are excluded too.
`country_indeed` filters the country when no `location` is supplied; with a
location, it helps resolve the requested city (default country: USA). An unknown
city returns no results rather than silently broadening the search. City filters
cannot disambiguate identical city names in different countries. Use
`country_indeed="worldwide"` without a location for a global search.
The API-provided application URL is returned as `job_url`; it can be an employer
ATS link or an intermediary link. If absent, the Freehire job page is used.
Freehire's standard search returns a
description preview; `fetch_description=True` requests full descriptions in the
selected `description_format`.

```python
jobs = scrape_jobs(
    site_name="freehire",
    search_term="python",
    country_indeed="worldwide",
    is_remote=True,
    results_wanted=5,
    fetch_description=True,
)
```

`offset + limit` is bounded to 10,000 by the API; the adapter stops at this bound.
`hours_old` rounds up to whole days against the source's `posted_at`, not the time
Freehire discovered the posting. `distance`, `easy_apply`, and LinkedIn-specific
options are not supported. Unsupported employment types do not apply a filter.
City names are resolved at runtime through `/geo/cities`; no additional skill or
category filters are exposed, so this adapter does not fetch the entire facet
vocabulary. Failed requests (including HTTP 429) stop the search and return any
results already collected, with a logged warning; do not use proxies to bypass
the API's published limits. Full descriptions reflect the stored source content
and may themselves be short.


## Notes
* Indeed is the best scraper currently with no rate limiting.  
* Indeed filters `hours_old` on when a job was added to Indeed, while `date_posted` is when the employer published it, so it can be older.  
* All the job board endpoints are capped at around 1000 jobs on a given search.  
* LinkedIn is the most restrictive and usually rate limits around the 10th page with one ip. Proxies are a must basically.
* Glassdoor rate limits after about 30 requests per ip, which `fetch_description` reaches quickly.
* Freehire is an API integration, not an HTML scraper. Its API publishes request budgets (currently 600 requests/minute for search and 300 requests/minute for full-description search); the adapter sends a `python-jobspy` User-Agent.

## Frequently Asked Questions

**Q: Why is Indeed giving unrelated roles?**  
**A:** Indeed searches the description too.

- use - to remove words
- "" for exact match

Example of a good Indeed query

```py
search_term='"engineering intern" software summer (java OR python OR c++) 2025 -tax -marketing'
```

This searches the description/title and must include software, summer, 2025, one of the languages, engineering intern exactly, no tax, no marketing.

---

**Q: No results when using "google"?**  
**A:** Google Jobs is currently unavailable.

---

**Q: Received a response code 429?**  
**A:** This indicates that you have been blocked by the job board site for sending too many requests. All of the job board sites are aggressive with blocking. We recommend:

- Wait some time between scrapes (site-dependent).
- Try using the proxies param to change your IP address.

---

### JobPost Schema

```plaintext
JobPost
├── title
├── company
├── company_url
├── job_url
├── location
│   ├── country
│   ├── city
│   ├── state
├── is_remote
├── description
├── job_type: fulltime, parttime, internship, contract
├── job_function
│   ├── interval: yearly, monthly, weekly, daily, hourly
│   ├── min_amount
│   ├── max_amount
│   ├── currency
│   └── salary_source: direct_data, description (parsed from posting)
├── date_posted
└── emails

Linkedin specific
└── job_level

Linkedin & Indeed specific
└── company_industry

Indeed specific
├── company_country
├── company_addresses
├── company_employees_label
├── company_revenue_label
├── company_description
└── company_logo

Naukri specific
├── skills
├── experience_range
├── company_rating
├── company_reviews_count
├── vacancy_count
└── work_from_home_type
```
