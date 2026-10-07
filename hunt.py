import csv
import pandas as pd
from datetime import datetime
from jobspy import scrape_jobs

search_terms = [
    "React Native Developer",
    "Mobile App Developer",
    "Frontend Developer React Native",
    "React Developer Mobile"
]

locations = [
    "Lagos, Nigeria",
    "Abuja, Nigeria",
    "Oyo, Nigeria",
    "Ogun, Nigeria",
    "Remote"
]

all_jobs = []

for term in search_terms:
    for location in locations:
        print(f"\n🔍 Searching for {term} in {location}...")
        try:
            jobs = scrape_jobs(
                site_name=["indeed", "linkedin", "google"],
                search_term=term,
                google_search_term=f"{term} jobs near {location} since last week",
                location=location,
                results_wanted=40,
                hours_old=168,
                country_indeed="Nigeria",
                linkedin_fetch_description=False,
            )
            print(f" Found {len(jobs)} jobs for {term} in {location}")
            if not jobs.empty:
                all_jobs.append(jobs)
        except Exception as e:
            print(f" Error fetching {term} in {location}: {e}")

if all_jobs:
    final_jobs = pd.concat(all_jobs).drop_duplicates(subset=["title", "company", "site"], keep="first")
    final_jobs.sort_values(by="date_posted", ascending=False, inplace=True)

    columns_to_keep = [
        "title", "company", "location", "via", "site", "date_posted",
        "job_url", "is_remote", "salary", "job_type", "description"
    ]

    for col in columns_to_keep:
        if col not in final_jobs.columns:
            final_jobs[col] = ""

    final_jobs = final_jobs[columns_to_keep]

    final_jobs.rename(columns={
        "title": "Job Title",
        "company": "Company",
        "location": "Location",
        "via": "Posted Via",
        "site": "Source Site",
        "date_posted": "Date Posted",
        "job_url": "Job URL",
        "is_remote": "Remote",
        "salary": "Salary",
        "job_type": "Job Type",
        "description": "Description",
    }, inplace=True)

    final_jobs.fillna("N/A", inplace=True)
    final_jobs["Description"] = final_jobs["Description"].astype(str) + "..."
    final_jobs.sort_values(by=["Location", "Job Title"], inplace=True)
    filename = f"Jobs_results_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"
    final_jobs.to_csv(filename, quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False, encoding="utf-8-sig")

    print(f"\n Saved clean, formatted results to: {filename}")
else:
    print("\n No jobs found. Try adjusting your parameters.")
