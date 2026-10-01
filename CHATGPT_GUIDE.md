# ChatGPT Deep Research Integration Guide

This guide enables ChatGPT and other LLMs to effectively use JobSpy for job market research, BD intelligence, and automated job searches.

## Quick Start for ChatGPT

### Installation Check
```python
# First, verify JobSpy is installed
try:
    from jobspy import scrape_jobs
    print("JobSpy is ready!")
except ImportError:
    import subprocess
    subprocess.run(["pip", "install", "python-jobspy"])
    from jobspy import scrape_jobs
```

### Basic Search Pattern
```python
from jobspy import scrape_jobs
import json

# Search for jobs
jobs = scrape_jobs(
    site_name=["indeed", "linkedin"],
    search_term="YOUR_SEARCH_TERM",
    location="LOCATION",
    results_wanted=15,
    verbose=0
)

# Convert to JSON for analysis
result = {
    "count": len(jobs),
    "jobs": jobs.to_dict(orient="records")
}
print(json.dumps(result, indent=2, default=str))
```

---

## Prompt Templates for ChatGPT

### 1. General Job Search
**User Prompt:**
> "Find [NUMBER] [JOB_TITLE] jobs in [LOCATION]"

**ChatGPT Action:**
```python
from jobspy import scrape_jobs
import json

jobs = scrape_jobs(
    site_name=["indeed", "linkedin"],
    search_term="[JOB_TITLE]",
    location="[LOCATION]",
    results_wanted=[NUMBER],
    verbose=0
)

# Display results
for _, job in jobs.head(10).iterrows():
    print(f"• {job['title']} at {job['company']}")
    print(f"  Location: {job['location']}")
    print(f"  URL: {job['job_url']}\n")
```

### 2. Remote Job Search
**User Prompt:**
> "Find remote [JOB_TITLE] jobs posted in the last [HOURS] hours"

**ChatGPT Action:**
```python
jobs = scrape_jobs(
    site_name=["indeed", "linkedin"],
    search_term="[JOB_TITLE]",
    is_remote=True,
    hours_old=[HOURS],
    results_wanted=20,
    verbose=0
)
```

### 3. Salary Research
**User Prompt:**
> "What's the salary range for [JOB_TITLE] in [LOCATION]?"

**ChatGPT Action:**
```python
jobs = scrape_jobs(
    site_name=["indeed", "glassdoor"],
    search_term="[JOB_TITLE]",
    location="[LOCATION]",
    results_wanted=50,
    verbose=0
)

# Analyze salary data
salaries = jobs[jobs['min_amount'].notna()][['title', 'company', 'min_amount', 'max_amount', 'interval']]
print(f"Salary data from {len(salaries)} postings:")
print(f"Range: ${salaries['min_amount'].min():,.0f} - ${salaries['max_amount'].max():,.0f}")
print(f"Median: ${salaries[['min_amount', 'max_amount']].mean().mean():,.0f}")
```

### 4. Company-Specific Search
**User Prompt:**
> "Find all jobs at [COMPANY_NAME]"

**ChatGPT Action:**
```python
jobs = scrape_jobs(
    site_name=["indeed"],
    search_term=f'"{[COMPANY_NAME]}"',  # Exact match
    results_wanted=50,
    verbose=0
)

company_jobs = jobs[jobs['company'].str.contains('[COMPANY_NAME]', case=False, na=False)]
print(f"Found {len(company_jobs)} jobs at [COMPANY_NAME]")
```

### 5. BD Intelligence - Hiring Trends
**User Prompt:**
> "Which companies are hiring the most [JOB_TYPE] in [INDUSTRY/LOCATION]?"

**ChatGPT Action:**
```python
jobs = scrape_jobs(
    site_name=["indeed", "linkedin"],
    search_term="[JOB_TYPE]",
    location="[LOCATION]",
    results_wanted=100,
    verbose=0
)

# Analyze by company
company_counts = jobs['company'].value_counts().head(15)
print("Top Hiring Companies:")
for company, count in company_counts.items():
    print(f"  {company}: {count} openings")
```

### 6. Federal/Cleared Job Search
**User Prompt:**
> "Find [CLEARANCE_LEVEL] cleared [JOB_TITLE] positions"

**ChatGPT Action:**
```python
jobs = scrape_jobs(
    site_name=["indeed", "linkedin"],
    search_term=f"[JOB_TITLE] [CLEARANCE_LEVEL]",
    location="Washington, DC",
    results_wanted=30,
    verbose=0
)
```

### 7. Competitor Analysis
**User Prompt:**
> "What positions are [COMPETITOR_COMPANY] hiring for?"

**ChatGPT Action:**
```python
jobs = scrape_jobs(
    site_name=["indeed"],
    search_term=f'"{[COMPETITOR_COMPANY]}"',
    results_wanted=50,
    verbose=0
)

# Filter and analyze
competitor_jobs = jobs[jobs['company'].str.contains('[COMPETITOR_COMPANY]', case=False, na=False)]
role_distribution = competitor_jobs['title'].value_counts()
print(f"Roles at [COMPETITOR_COMPANY]:\n{role_distribution}")
```

---

## CLI Usage for ChatGPT Code Execution

The CLI provides a simpler interface when using code execution:

```bash
# Basic search
python jobspy_cli.py --search "data scientist" --location "NYC" --format json

# Remote jobs with filters
python jobspy_cli.py --search "software engineer" --remote --hours 48 --results 20

# Multiple sites
python jobspy_cli.py --search "project manager" --sites indeed,linkedin,glassdoor

# JSON input mode (for complex queries)
echo '{"search_term": "python developer", "location": "Remote", "results_wanted": 10}' | python jobspy_cli.py --json-input
```

---

## Output Formats

### JSON Format (Recommended for LLM)
```json
{
  "success": true,
  "count": 15,
  "jobs": [
    {
      "site": "indeed",
      "title": "Software Engineer",
      "company": "TechCorp",
      "location": "San Francisco, CA",
      "job_type": "fulltime",
      "min_amount": 120000,
      "max_amount": 180000,
      "interval": "yearly",
      "job_url": "https://indeed.com/...",
      "description": "Job description here...",
      "date_posted": "2025-01-15",
      "is_remote": false
    }
  ]
}
```

### Key Fields for Analysis
| Field | Description | Use Case |
|-------|-------------|----------|
| `title` | Job title | Role identification |
| `company` | Company name | BD targeting |
| `location` | Job location | Geographic analysis |
| `min_amount`/`max_amount` | Salary range | Compensation research |
| `interval` | Salary period | Normalize salaries |
| `job_url` | Direct link | Reference/verification |
| `description` | Full job description | Skills extraction |
| `date_posted` | Posting date | Freshness filter |
| `is_remote` | Remote flag | Work arrangement |

---

## Best Practices for ChatGPT

### 1. Start with Indeed
Indeed has the best coverage and no rate limiting. Start searches here:
```python
jobs = scrape_jobs(site_name=["indeed"], ...)
```

### 2. Use Appropriate Result Counts
- Quick overview: `results_wanted=10`
- Standard search: `results_wanted=20`
- Comprehensive analysis: `results_wanted=50-100`

### 3. Filter by Recency
Use `hours_old` for fresh postings:
```python
jobs = scrape_jobs(..., hours_old=24)  # Last 24 hours
jobs = scrape_jobs(..., hours_old=72)  # Last 3 days
jobs = scrape_jobs(..., hours_old=168) # Last week
```

### 4. Handle Empty Results
```python
jobs = scrape_jobs(...)
if jobs.empty:
    print("No jobs found. Try broadening your search.")
else:
    # Process results
```

### 5. Use Boolean Search Operators
Indeed supports advanced search:
```python
# Must include term
search_term = '"software engineer"'

# Exclude terms
search_term = 'python developer -junior -entry'

# OR combinations
search_term = '(python OR java) developer senior'
```

---

## Advanced Use Cases

### BD Intelligence: Growth Signals
```python
def identify_growth_companies(industry_keyword, location):
    """Find companies with high hiring activity (growth signals)"""
    jobs = scrape_jobs(
        site_name=["indeed", "linkedin"],
        search_term=industry_keyword,
        location=location,
        results_wanted=100,
        hours_old=168,  # Last week
        verbose=0
    )

    company_analysis = jobs.groupby('company').agg({
        'title': 'count',
        'location': lambda x: list(set(x))
    }).rename(columns={'title': 'openings'})

    growth_companies = company_analysis[company_analysis['openings'] >= 5]
    return growth_companies.sort_values('openings', ascending=False)
```

### CIS Labor Category Mapping
```python
def extract_role_requirements(job_title, location):
    """Extract duties and qualifications for labor category mapping"""
    jobs = scrape_jobs(
        site_name=["indeed"],
        search_term=job_title,
        location=location,
        results_wanted=20,
        linkedin_fetch_description=True,
        verbose=0
    )

    # Return descriptions for analysis
    return jobs[['title', 'company', 'description']].to_dict(orient='records')
```

### Competitor Staffing Monitor
```python
COMPETITOR_STAFFING = [
    "Insight Global", "TEKsystems", "Apex Systems",
    "Belcan", "GDIT", "Booz Allen Hamilton"
]

def monitor_competitors():
    """Monitor hiring activity at competitor staffing companies"""
    results = {}
    for company in COMPETITOR_STAFFING:
        jobs = scrape_jobs(
            site_name=["indeed"],
            search_term=f'"{company}"',
            results_wanted=30,
            verbose=0
        )
        results[company] = {
            "openings": len(jobs),
            "roles": jobs['title'].tolist()[:10]
        }
    return results
```

---

## Troubleshooting

### Rate Limiting (429 Error)
- **Solution**: Use proxies or switch to Indeed (no rate limiting)
```python
jobs = scrape_jobs(..., proxies=["proxy1:port", "proxy2:port"])
```

### No Results
- Broaden search term
- Remove location filter
- Try different sites
- Check spelling

### LinkedIn Issues
- LinkedIn is restrictive; use proxies
- Set `linkedin_fetch_description=False` for faster results
- Consider using Indeed as primary source

---

## Reference

### Supported Sites
| Site | Coverage | Notes |
|------|----------|-------|
| `indeed` | Global | Best choice, no rate limits |
| `linkedin` | Global | Requires proxies for heavy use |
| `glassdoor` | Major countries | Includes company reviews |
| `zip_recruiter` | US/Canada | Good salary data |
| `google` | Global | Aggregates multiple sources |
| `bayt` | Middle East | Regional specialist |
| `naukri` | India | Regional specialist |

### Full Parameter List
See `tool_manifest.json` for complete API documentation.
