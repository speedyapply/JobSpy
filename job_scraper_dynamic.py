import csv
import datetime
import json
import os

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

# Read dynamic user-specific config.json
with open("config.json", "r") as f:
    config = json.load(f)

search_terms = config.get("search_terms", [])
results_wanted = config.get("results_wanted", 100)
max_days_old = config.get("max_days_old", 2)
target_state = config.get("target_state", "NY")
user_email = config.get("user_email", "unknown@domain.com")


def scrape_jobs(search_terms, results_wanted, max_days_old, target_state):
    """Scrape jobs from multiple sources and filter by state."""
    all_jobs = []
    today = datetime.date.today()
    
    print("\n🔎 DEBUG: Fetching jobs for search terms:", search_terms)

    for search_term in search_terms:
        for source_name, source_class in sources.items():
            print(f"\n🚀 Scraping {search_term} from {source_name}...")

            scraper = source_class()
            search_criteria = ScraperInput(
                site_type=[source_name],
                search_term=search_term,
                results_wanted=results_wanted,
            )

            job_response = scraper.scrape(search_criteria)

            for job in job_response.jobs:
                location_city = job.location.city.strip() if job.location.city else "Unknown"
                location_state = job.location.state.strip().upper() if job.location.state else "Unknown"
                location_country = str(job.location.country) if job.location.country else "Unknown"

                if not any(term.lower() in job.title.lower() for term in search_terms):
                    print(f"🚫 Excluding: {job.title} (Doesn't match search terms)")
                    continue

                if job.date_posted and (today - job.date_posted).days <= max_days_old:
                    if location_state == target_state or job.is_remote:
                        print(f"✅ MATCH: {job.title} - {location_city}, {location_state} (Posted {job.date_posted})")
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
                            "Location City": location_city,
                            "Location State": location_state,
                            "Location Country": location_country,
                            "Job URL": job.job_url,
                            "Job Description": job.description.replace(",", "") if job.description else "No description available",
                            "Job Source": source_name
                        })
                    else:
                        print(f"❌ Ignored (Wrong State): {job.title} - {location_city}, {location_state}")
                else:
                    print(f"⏳ Ignored (Too Old): {job.title} - {location_city}, {location_state}")

    print(f"\n✅ {len(all_jobs)} jobs retrieved for user {user_email}")
    return all_jobs


def save_jobs_to_csv(jobs, user_email):
    """Save job data to a user-specific CSV file using custom delimiter."""
    if not jobs:
        print("⚠️ No jobs found matching criteria.")
        return

    # Clean the email to create a safe filename
    safe_email = user_email.replace("@", "_at_").replace(".", "_")
    filename = f"jobspy_output_dynamic_{safe_email}.csv"

    # Remove old file if it exists
    if os.path.exists(filename):
        os.remove(filename)

    fieldnames = [
        "Job ID", "Job Title (Primary)", "Company Name", "Industry",
        "Experience Level", "Job Type", "Is Remote", "Currency",
        "Salary Min", "Salary Max", "Date Posted", "Location City",
        "Location State", "Location Country", "Job URL", "Job Description",
        "Job Source", "User Email"
    ]

    with open(filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter="|")
        writer.writeheader()
        for job in jobs:
            job["User Email"] = user_email
            writer.writerow(job)

    print(f"📄 File saved: {filename} ({len(jobs)} entries)")
    return filename


# Run the scraper and save the results to a user-specific output file
job_data = scrape_jobs(
    search_terms=search_terms,
    results_wanted=results_wanted,
    max_days_old=max_days_old,
    target_state=target_state
)

output_filename = save_jobs_to_csv(job_data, user_email)
