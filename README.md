<h1 align="center">
  <a href="https://github.com/speedyapply/JobSpy"><img src="https://github.com/user-attachments/assets/dcb90340-9469-4808-bc51-868e59a000e0" alt="JobSpy" width="320"></a>
</h1>

<p align="center">
  <a href="https://pypi.org/project/python-jobspy/"><img src="https://img.shields.io/pypi/v/python-jobspy" alt="PyPI version"></a>
  <a href="https://pypi.org/project/python-jobspy/"><img src="https://img.shields.io/pypi/pyversions/python-jobspy" alt="Python versions"></a>
  <a href="https://pepy.tech/projects/python-jobspy"><img src="https://static.pepy.tech/badge/python-jobspy/month" alt="Downloads per month"></a>
  <a href="https://github.com/speedyapply/JobSpy/actions/workflows/ci.yml"><img src="https://github.com/speedyapply/JobSpy/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://github.com/speedyapply/JobSpy/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/python-jobspy" alt="License: MIT"></a>
  <a href="https://discord.gg/v7WdHnrNcN"><img src="https://img.shields.io/discord/1227411661221269565?label=discord&logo=discord&logoColor=white" alt="Discord"></a>
</p>

**JobSpy** is a job scraping library that aggregates jobs from popular job boards with one tool:

- Scrapes job postings from **LinkedIn**, **Indeed**, **Glassdoor**, **ZipRecruiter**, **Bayt**, **Naukri**, **BDJobs**, **HelloWork** & **TechJobs.vn** concurrently
- Aggregates the job postings in a dataframe
- Proxy support to bypass blocking

<p align="center">
  <a href="https://github.com/speedyapply/JobSpy"><img src="https://github.com/cullenwatson/JobSpy/assets/78247585/ec7ef355-05f6-4fd3-8161-a817e31c5c57" alt="JobSpy demo"></a>
</p>

## Installation

```
pip install -U python-jobspy
```

_Python version >= [3.10](https://www.python.org/downloads/release/python-3100/) required_

## Usage

```python
from jobspy import scrape_jobs

jobs = scrape_jobs(
    site_name=["indeed", "linkedin", "zip_recruiter", "glassdoor"],  # also "bayt", "naukri", "bdjobs", "hellowork", "techjobs"
    search_term="software engineer",
    location="San Francisco, CA",
    results_wanted=20,
    hours_old=72,
    country_indeed="USA",
    # fetch_description=True,  # read each job's page on boards whose search results have no description (slower)
    # proxies=["user:pass@host:port", "localhost"],
)
print(f"Found {len(jobs)} jobs")
print(jobs.head())
jobs.to_csv("jobs.csv", index=False)
```

## Output

```
SITE           TITLE                             COMPANY           LOCATION                JOB_TYPE  INTERVAL  MIN_AMOUNT  MAX_AMOUNT  JOB_URL                                            DESCRIPTION
indeed         Software Engineer                 AMERICAN SYSTEMS  Arlington, VA, USA      None      yearly    150000      200000      https://www.indeed.com/viewjob?jk=5e409e577046...  THIS POSITION COMES WITH A 10K SIGNING BONUS!...
indeed         Senior Software Engineer          TherapyNotes.com  Philadelphia, PA, USA   fulltime  yearly    110000      135000      https://www.indeed.com/viewjob?jk=da39574a40cb...  About Us TherapyNotes is the national leader i...
linkedin       Software Engineer - Early Career  Lockheed Martin   Sunnyvale, CA, USA      fulltime  yearly    None        None        https://www.linkedin.com/jobs/view/3693012711      Description:By bringing together people that u...
linkedin       Full-Stack Software Engineer      Rain              New York, NY, USA       fulltime  yearly    None        None        https://www.linkedin.com/jobs/view/3696158877      Rain’s mission is to create the fastest and ea...
zip_recruiter  Software Engineer - New Grad      ZipRecruiter      Santa Monica, CA, USA   fulltime  yearly    130000      150000      https://www.ziprecruiter.com/jobs/ziprecruiter...  We offer a hybrid work environment. Most US-ba...
zip_recruiter  Software Developer                TEKsystems        Phoenix, AZ, USA        fulltime  hourly    65          75          https://www.ziprecruiter.com/jobs/teksystems-0...  Top Skills' Details• 6 years of Java developme...

```

## Command line

The package installs a `jobspy` command whose options mirror the `scrape_jobs()` parameters below; `jobspy -h` lists them, the output fields and exit codes.

```
uv tool install python-jobspy

jobspy "software engineer" --site indeed,linkedin --location Chicago -n 20
jobspy nurse --site indeed,linkedin --hours-old 24 -o jobs.jsonl
jobspy "data analyst" --remote --fields title,company,job_url
```

## MCP server

[`mcp-jobspy`](https://pypi.org/project/mcp-jobspy/) is an MCP server that runs with `uvx mcp-jobspy@latest`. See [mcp/README.md](https://github.com/speedyapply/JobSpy/blob/main/mcp/README.md) for setup, tools and proxies.

**Standard config** works for most clients:

```json
{
  "mcpServers": {
    "jobspy": {
      "command": "uvx",
      "args": ["mcp-jobspy@latest"]
    }
  }
}
```

## Parameters for `scrape_jobs()`

```plaintext
Optional
├── site_name (list|str): 
|    linkedin, zip_recruiter, indeed, glassdoor, google, bayt, bdjobs, naukri, hellowork, techjobs
|    (default is all)
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
|    fulltime, parttime, contract, temporary, internship, perdiem, other, volunteer
│
├── proxies (list|str): 
|    in format ['user:pass@host:port', 'localhost'], or a single proxy as a string
|    each job board scraper will round robin through the proxies
|    socks proxies on LinkedIn, Indeed and BDJobs need pip install "requests[socks]"
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
|    markdown, html, plain (Format type of the job descriptions. Default is markdown.)
│
├── offset (int): 
|    skips that many results (e.g. 25 skips the first 25 and starts from the 26th)
│
├── hours_old (int): 
|    filters jobs by the number of hours since the job was posted 
|    (Glassdoor filters by whole days, so it rounds up to the next day.)
│
├── verbose (int) {0, 1, 2}: 
|    Controls the verbosity of the runtime printouts 
|    (0 prints only errors, 1 is errors+warnings, 2 is all logs. Default is 1.)
│
├── fetch_description (bool): 
|    for boards whose search results don't include the job description: fetches each job's
|    page for the description and other details (e.g. job type). Without it these are empty
|    for those boards. Adds one request per job, so use proxies for larger searches
│
├── linkedin_fetch_description (bool): 
|    deprecated, use fetch_description (still works; removed in 2.0)
│
├── linkedin_company_ids (list[int]): 
|    searches for linkedin jobs with specific company ids
|
├── country_indeed (str): 
|    filters the country on Indeed & Glassdoor (default is usa; see below for the names)
|
├── enforce_annual_salary (bool): 
|    converts wages to annual salary
|
├── ca_cert (str)
|    path to CA Certificate file for proxies
```

## Supported Countries for Job Searching

### LinkedIn

LinkedIn searches globally & uses only the `location` parameter. 

### ZipRecruiter

ZipRecruiter searches for jobs in **US/Canada** & uses only the `location` parameter.

### Indeed / Glassdoor

Indeed & Glassdoor support most countries, chosen with the `country_indeed` parameter (default `usa`). Additionally, use the `location`
parameter to narrow down the location, e.g. city & state if necessary. 

You can specify the following countries when searching on Indeed (use the exact name, * indicates support for Glassdoor):

|                      |              |            |                |
|----------------------|--------------|------------|----------------|
| Argentina*           | Australia*   | Austria*   | Bahrain        |
| Belgium*             | Brazil*      | Canada*    | Chile          |
| China                | Colombia     | Costa Rica | Czech Republic |
| Denmark              | Ecuador      | Egypt      | Finland        |
| France*              | Germany*     | Greece     | Hong Kong*     |
| Hungary              | India*       | Indonesia  | Ireland*       |
| Israel               | Italy*       | Japan      | Kuwait         |
| Luxembourg           | Malaysia*    | Mexico*    | Morocco        |
| Netherlands*         | New Zealand* | Nigeria    | Norway         |
| Oman                 | Pakistan     | Panama     | Peru           |
| Philippines          | Poland       | Portugal   | Qatar          |
| Romania              | Saudi Arabia | Singapore* | South Africa   |
| South Korea          | Spain*       | Sweden     | Switzerland*   |
| Taiwan               | Thailand     | Turkey     | Ukraine        |
| United Arab Emirates | UK*          | USA*       | Uruguay        |
| Venezuela            | Vietnam*     |            |                |

### Bayt

Bayt searches all countries unless `location` names one it covers, e.g. `"Dubai, UAE"` or `"Saudi Arabia"`.

### BDJobs

BDJobs searches Bangladesh. `location` takes a division or district, e.g. `"Dhaka"` or `"Chattogram Division"`.

### Naukri

Naukri searches India. `location` takes a city, e.g. `"Pune"`.

### HelloWork

HelloWork searches France. `location` takes a French city, postcode or region, e.g. `"Lyon"`. Most jobs are posted in French, so French search terms find more.

### TechJobs.vn

TechJobs.vn searches tech jobs in Vietnam, collected hourly from each employer's own careers page or ATS. It reads the site's public JSON feed ([OpenAPI](https://techjobs.vn/feeds/openapi.json)), so no proxy is needed. `location` takes a city, e.g. `"Hanoi"`, `"Ho Chi Minh City"` or `"Da Nang"`; `is_remote` returns remote jobs. `job_url` is the job's page on techjobs.vn and `job_url_direct` the employer's own posting. With `fetch_description`, `description` holds a short summary generated from the job's tagged fields (role, skills, experience), not the full JD.


## Notes
* Indeed is the best scraper currently with no rate limiting.  
* Indeed's `date_posted` is the day a job was added to Indeed, the same date `hours_old` filters on.  
* Most job board endpoints are capped at around 1000 jobs on a given search.  
* LinkedIn rate limits bursts of requests with a 429, which clears within about a minute. Use proxies for larger searches.
* Glassdoor rate limits above about 2 requests a second.

## Frequently Asked Questions

**Q: How do I tell a blocked board from one with no jobs?**  
**A:** Failures and ignored options are logged as they happen, and the result's `attrs` carry the same messages so your code can read them:

```py
jobs.attrs["errors"]    # {"linkedin": "response status code 429 (blocked: use a proxy)"}
jobs.attrs["warnings"]  # {"bdjobs": ["job_type internship isn't supported, ignoring it"]}
```

---

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
**A:** The board blocked you for sending too many requests. All of the job board sites are aggressive with blocking. We recommend:

- Wait some time between scrapes (site-dependent).
- Try using the proxies param to change your IP address.

---

## JobPost Schema

```plaintext
JobPost
├── id
├── site
├── job_url
├── job_url_direct
├── title
├── company
├── location
├── date_posted
├── job_type: fulltime, parttime, internship, contract, temporary, ...
├── salary_source: direct_data, description (parsed from posting)
├── interval: yearly, monthly, weekly, daily, hourly
├── min_amount
├── max_amount
├── currency
├── is_remote
├── job_level
├── job_function
├── listing_type
├── emails
├── description
├── company_industry
├── company_url
├── company_logo
├── company_url_direct
├── company_addresses
├── company_num_employees
├── company_revenue
├── company_description
├── skills
├── experience_range
├── company_rating
├── company_reviews_count
├── vacancy_count
└── work_from_home_type
```

A column is empty when the job board doesn't provide it.
