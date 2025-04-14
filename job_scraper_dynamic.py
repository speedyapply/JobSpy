import csv
import datetime
import json
import os
import re
from jobspy.google import Google
from jobspy.linkedin import LinkedIn
from jobspy.indeed import Indeed
from jobspy.model import ScraperInput

# Define job sources
sources = {
    "google": Google,
    "linkedin": LinkedIn,
    "indeed": Indeed,
}

# Load user config
with open("config.json", "r") as file:
    config = json.load(file)

user_email = config.get("user_email")
search_terms = [term.strip() for term in config.get("search_terms", "").split(",")]
results_wanted = int(config.get("results_wanted", 100))
max_days_old = int(config.get("max_days_old", 2))
target_state = config.get("target_state", "NY")

# Sanitize email for filename
safe_email = re.sub(r'[@.]', lambda x: '_at_' if x.group() == '@' else '_', user_email)
output_filename = f"jobspy_output_dynamic_{safe_email}.csv"

def scrape_jobs():
    all_jobs = []
    today = datetime.date.today()

    print(f"\n🔎 Fetching jobs for: {search_terms}")

    for search_term in search_terms:
        for source_name, source_class in sources.items():
            print(f"🚀 Scraping {search_term} from {source_name}...")
            scraper = source_class()
            input_params = ScraperInput(
                site_type=[source_name],
                search_term=search_term,
                results_wanted=results_wanted,
            )
            results = scraper.scrape(input_params)

            for job in results.jobs:
                location_state = job.location.state.strip().upper() if job.location and job.location.state else "Unknown"
                if job.date_posted and (today - job.date_posted).days <= max_days_old:
                    if location_state == target_state or job.is_remote:
                        all_jobs.append({
                            "Job ID": job.id,
                            "Job Title (Primary)": job.title,
                            "Company Name": job.company_name or "Unknown",
                            "Industry": job.company_industry or "Not Provided",
                            "Experience Level": job.job_level or "Not Provided",
                            "Job Type": job.job_type[0].name if job.job_type else "Not Provided",
                            "Is Remote": job.is_remote,
                            "Currency": job.compensation.currency if job.compensation else "",
                            "Salary Min": job.compensation.min_amount if job.compensation else "",
                            "Salary Max": job.compensation.max_amount if job.compensation else "",
                            "Date Posted": job.date_posted.strftime("%Y-%m-%d") if job.date_posted else "Not Provided",
                            "Location City": job.location.city if job.location and job.location.city else "Unknown",
                            "Location State": location_state,
                            "Location Country": str(job.location.country) if job.location and job.location.country else "Unknown",
                            "Job URL": job.job_url,
                            "Job Description": job.description.replace(",", "") if job.description else "No description",
                            "Job Source": source_name
                        })

    return all_jobs

def save_jobs_to_csv(jobs, filename):
    if not jobs:
        print("⚠️ No jobs found.")
        return

    fieldnames = list(jobs[0].keys())
    header = "|~|".join(fieldnames)
    records = [header]

    for job in jobs:
        row = [str(job.get(field, "Not Provided")).replace(",", "") for field in fieldnames]
        records.append("|~|".join(row))

    output = ",".join(records)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"✅ Saved {len(jobs)} jobs to {filename}")

# Run
scraped_jobs = scrape_jobs()
save_jobs_to_csv(scraped_jobs, output_filename)
