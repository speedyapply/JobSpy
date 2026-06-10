from jobspy import scrape_jobs
import webbrowser
import os
import pandas as pd

# Run JobSpy for Indeed only
jobs = scrape_jobs(
    site_name="indeed",  # Only Indeed
    search_term="Cloud Engineer, DevOps Engineer",  # Your keywords
    location="Germany",  # Optional: location filter
    country_indeed="germany",  # Germany
    job_type="fulltime",  # Fulltime jobs only
    hours_old=48,  # Jobs posted in last 24 hours (latest)
    results_wanted=50,  # Number of results
)

print(f"Found {len(jobs)} jobs")
print(jobs.head())

# Select only desired columns
columns_to_show = ["site", "job_url", "job_url_direct", "title", "company", "location", "date_posted", "job_type"]
jobs_filtered = jobs[columns_to_show].copy()

# Make links clickable by converting URLs to HTML anchor tags
jobs_filtered["job_url"] = jobs_filtered["job_url"].apply(lambda x: f'<a href="{x}" target="_blank">View</a>' if pd.notna(x) else "")
jobs_filtered["job_url_direct"] = jobs_filtered["job_url_direct"].apply(lambda x: f'<a href="{x}" target="_blank">View</a>' if pd.notna(x) else "")

# Save to HTML and open in browser
html_file = "indeed_jobs.html"
jobs_filtered.to_html(html_file, index=False, escape=False)
print(f"Jobs saved to {html_file}")

# Open in default browser
webbrowser.open('file://' + os.path.realpath(html_file))
print(f"Opening {html_file} in browser...")