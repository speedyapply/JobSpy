# Germany IT Jobs Search - Usage Guide

## Overview

The `search_germany_jobs.py` script is designed to search for IT and Software Engineering jobs in Germany using the JobSpy library. It prioritizes Berlin-based positions and covers various IT-related fields.

## Features

- **Comprehensive IT Job Search**: Searches for multiple job titles including:
  - Software Engineer
  - Software Developer
  - DevOps Engineer
  - Site Reliability Engineer (SRE)
  - System Engineer
  - Backend Developer
  - Full Stack Developer
  - Python Developer
  - Java Developer

- **Location Priority**: Searches Berlin first, then broader Germany
- **Time Filter**: Only shows jobs posted in the last 7 days
- **Multiple Job Boards**: Searches Indeed, LinkedIn, and Google Jobs
- **Duplicate Removal**: Automatically removes duplicate job postings
- **Sorted Results**: Berlin jobs appear first, sorted by posting date

## Prerequisites

Ensure you have the JobSpy package installed:

```bash
pip install python-jobspy
```

Or if you're working with the repository directly:

```bash
pip install -e .
```

## Usage

### Basic Usage

Simply run the script:

```bash
python search_germany_jobs.py
```

### What the Script Does

1. **Searches Berlin specifically** for all defined job titles
2. **Searches Germany broadly** for all defined job titles
3. **Combines and deduplicates** results
4. **Sorts results** with Berlin jobs appearing first
5. **Saves to CSV** with a timestamp in the filename (e.g., `germany_it_jobs_20260204_190052.csv`)
6. **Displays a summary** including total jobs found and a sample of the first 5 results

### Output

The script generates a CSV file containing the following information for each job:
- Job title
- Company name
- Location
- Job type (full-time, part-time, contract, etc.)
- Job site (Indeed, LinkedIn, Google)
- Date posted
- Job URL
- Description
- Salary information (if available)
- And more...

### Example Output

```
================================================================================
Searching for IT/Software Engineering Jobs in Germany
================================================================================
Time filter: Jobs posted in the last 7 days
Job boards: indeed, linkedin, google
Locations: Berlin (priority), Germany (general)
================================================================================

Step 1: Searching for jobs in Berlin...
--------------------------------------------------------------------------------
  Searching: Software Engineer in Berlin...
    Found 15 jobs for 'Software Engineer' in Berlin
  Searching: DevOps Engineer in Berlin...
    Found 8 jobs for 'DevOps Engineer' in Berlin
  ...

Step 2: Searching for jobs in Germany (general)...
--------------------------------------------------------------------------------
  Searching: Software Engineer in Germany...
    Found 20 jobs for 'Software Engineer' in Germany
  ...

================================================================================
Total jobs found: 156
Results saved to: germany_it_jobs_20260204_190052.csv

Sample of results (first 5 jobs):
--------------------------------------------------------------------------------
title                          company              location           job_type  site     date_posted
Senior Software Engineer       SAP                  Berlin, Germany    fulltime  linkedin 2026-02-03
DevOps Engineer               Zalando SE           Berlin, Germany    fulltime  indeed   2026-02-02
...
================================================================================

✓ Successfully completed job search!
  Total unique jobs found: 156
```

## Customization

You can modify the script to customize your search:

### Change Search Terms

Edit the `search_terms` list in the `search_germany_it_jobs()` function:

```python
search_terms = [
    "Software Engineer",
    "DevOps Engineer",
    # Add your custom search terms here
]
```

### Change Time Filter

Modify the `hours_old` variable:

```python
hours_old = 24 * 7  # 7 days (default)
hours_old = 24 * 3  # 3 days
hours_old = 24 * 14  # 14 days (2 weeks)
```

### Change Job Boards

Modify the `sites` list:

```python
sites = ["indeed", "linkedin", "google"]  # Default
sites = ["indeed", "linkedin"]  # Only Indeed and LinkedIn
```

### Change Number of Results per Search

Modify the `results_wanted` parameter:

```python
jobs = scrape_jobs(
    # ...
    results_wanted=20,  # Default: 20 results per search term
    # ...
)
```

### Add More Locations

Add additional location searches in the script:

```python
# Search Munich
jobs = scrape_jobs(
    site_name=sites,
    search_term=search_term,
    location="Munich, Germany",
    results_wanted=20,
    hours_old=hours_old,
    country_indeed='Germany',
)
```

## Notes

- **Rate Limiting**: Job boards may rate-limit requests. If you get errors, try:
  - Adding delays between searches
  - Using fewer search terms
  - Using proxies (see JobSpy documentation)

- **Network Requirements**: The script requires internet access to scrape job boards

- **Search Quality**: For best results:
  - Use specific search terms
  - Adjust the time filter based on job market activity
  - Review the JobSpy documentation for advanced search options

## Troubleshooting

### No Jobs Found
- Check your internet connection
- Try increasing `hours_old` to search over a longer period
- Verify that the location is correctly specified
- Try different or more general search terms

### Rate Limited (Error 429)
- Wait a few minutes before running the script again
- Reduce the number of search terms
- Reduce `results_wanted` per search
- Consider using proxies (see JobSpy documentation)

### Module Not Found Error
```bash
# Install the package
pip install python-jobspy

# Or if working with the repository
pip install -e .
```

## Additional Resources

- [JobSpy GitHub Repository](https://github.com/cullenwatson/JobSpy)
- [JobSpy Documentation](https://github.com/cullenwatson/JobSpy#readme)

## License

This script uses the JobSpy library. Please refer to the JobSpy license for usage terms.
