import csv
import datetime
from jobspy.google import Google
from jobspy.linkedin import LinkedIn
from jobspy.indeed import Indeed
from jobspy.ziprecruiter import ZipRecruiter
from jobspy.model import ScraperInput

# Define job sources
SOURCES = {
    "google": Google,
    "linkedin": LinkedIn,
    "indeed": Indeed,
    "zip_recruiter": ZipRecruiter,
}

# Define search preferences
SEARCH_TERMS = ["Automation Engineer", "CRM Manager", "Implementation Specialist"]
RESULTS_WANTED = 200  # Fetch more jobs
MAX_DAYS_OLD = 2  # Fetch jobs posted in last 48 hours
TARGET_STATE = "NY"  # Only keep jobs from New York


def scrape_jobs(search_terms, results_wanted, max_days_old, target_state):
    """Scrape jobs from multiple sources and filter by state."""
    all_jobs = []
    today = datetime.date.today()
    print("\n🔎 DEBUG: Fetching jobs for search terms:", search_terms)

    for search_term in search_terms:
        for source_name, source_class in SOURCES.items():
            print(f"\n🚀 Scraping {search_term} from {source_name}...")

            scraper = source_class()
            search_criteria = ScraperInput(
                site_type=[source_name],
                search_term=search_term,
                results_wanted=results_wanted,
            )

            job_response = scraper.scrape(search_criteria)

            for job in job_response.jobs:
                # Normalize location fields
                location_city = job.location.city.strip() if job.location.city else "Unknown"
                location_state = job.location.state.strip().upper() if job.location.state else "Unknown"
                location_country = str(job.location.country) if job.location.country else "Unknown"

                # Debug: Show all jobs being fetched
                print(f"📍 Fetched Job: {job.title} - {location_city}, {location_state}, {location_country}")

                # Ensure the job is recent
                if job.date_posted and (today - job.date_posted).days <= max_days_old:
                    if location_state == target_state or job.is_remote:
                        print(f"✅ MATCH (In NY or Remote): {job.title} - {location_city}, {location_state} (Posted {job.date_posted})")

                        all_jobs.append({
                            "Job ID": job.id,
                            "Job Title (Primary)": job.title,
                            "Company Name": job.company_name if job.company_name else "Unknown",
                            "Industry": job.company_industry if job.company_industry else "Not Provided",
                            "Experience Level": job.job_level if job.job_level else "Not Provided",
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
                            "Job Description": job.description[:500] if job.description else "No description available",
                            "Job Source": source_name
                        })
                    else:
                        print(f"❌ Ignored (Wrong State): {job.title} - {location_city}, {location_state} (Posted {job.date_posted})")
                else:
                    print(f"⏳ Ignored (Too Old): {job.title} - {location_city}, {location_state} (Posted {job.date_posted})")

    print(f"\n✅ {len(all_jobs)} jobs retrieved in NY")
    return all_jobs


def save_jobs_to_csv(jobs, filename="jobspy_output.csv"):
    """Save job data to a CSV file."""
    if not jobs:
        print("⚠️ No jobs found matching criteria.")
        return

    fieldnames = [
        "Job ID", "Job Title (Primary)", "Company Name", "Industry",
        "Experience Level", "Job Type", "Is Remote", "Currency",
        "Salary Min", "Salary Max", "Date Posted", "Location City",
        "Location State", "Location Country", "Job URL", "Job Description",
        "Job Source"
    ]

    with open(filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(jobs)

    print(f"✅ Jobs saved to {filename} ({len(jobs)} entries)")


# Run the scraper with multiple job searches
job_data = scrape_jobs(
    search_terms=SEARCH_TERMS,
    results_wanted=RESULTS_WANTED,
    max_days_old=MAX_DAYS_OLD,
    target_state=TARGET_STATE
)

# Save results to CSV
save_jobs_to_csv(job_data)
