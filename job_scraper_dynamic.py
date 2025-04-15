import csv
import datetime
import os
import sys
import json
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

def sanitize_email(email):
    """Sanitize email to use in filename."""
    return email.replace("@", "_at_").replace(".", "_")

def scrape_jobs(search_terms, results_wanted, max_days_old, target_state):
    all_jobs = []
    today = datetime.date.today()

    print("\n🔎 Fetching jobs for search terms:", search_terms)

    for search_term in search_terms:
        for source_name, source_class in sources.items():
            print(f"\n🚀 Scraping '{search_term}' from {source_name}...")

            scraper = source_class()
            search_criteria = ScraperInput(
                site_type=[source_name],
                search_term=search_term,
                results_wanted=results_wanted,
            )

            try:
                job_response = scraper.scrape(search_criteria)
            except Exception as e:
                print(f"❌ Error scraping from {source_name} with term '{search_term}': {e}")
                continue

            for job in job_response.jobs:
                location_city = job.location.city.strip() if job.location.city else "Unknown"
                location_state = job.location.state.strip().upper() if job.location.state else "Unknown"
                location_country = str(job.location.country) if job.location.country else "Unknown"

                # Match job title to search term
                if not any(term.lower() in job.title.lower() for term in search_terms):
                    continue

                # Filter by date and location
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
                            "Location City": location_city,
                            "Location State": location_state,
                            "Location Country": location_country,
                            "Job URL": job.job_url,
                            "Job Description": job.description.replace(",", "") if job.description else "No description available",
                            "Job Source": source_name
                        })

    print(f"\n✅ {len(all_jobs)} jobs retrieved")
    return all_jobs

def save_jobs_to_csv(jobs, filename):
    """Save job data to a CSV file with custom formatting."""
    if not jobs:
        print("⚠️ No jobs found matching criteria.")
        return

    if os.path.exists(filename):
        os.remove(filename)

    fieldnames = [
        "Job ID", "Job Title (Primary)", "Company Name", "Industry",
        "Experience Level", "Job Type", "Is Remote", "Currency",
        "Salary Min", "Salary Max", "Date Posted", "Location City",
        "Location State", "Location Country", "Job URL", "Job Description",
        "Job Source"
    ]

    header_record = "|~|".join(fieldnames)
    records = [header_record]

    for job in jobs:
        row = []
        for field in fieldnames:
            value = str(job.get(field, "")).strip()
            if not value:
                value = "Not Provided"
            value = value.replace(",", "")
            row.append(value)
        record = "|~|".join(row)
        records.append(record)

    output = ",".join(records)
    with open(filename, "w", encoding="utf-8") as file:
        file.write(output)

    print(f"✅ Jobs saved to {filename} ({len(jobs)} entries)")

# MAIN
if __name__ == "__main__":
    try:
        if len(sys.argv) >= 6:
            # CLI input
            search_terms_str = sys.argv[1]
            results_wanted = int(sys.argv[2])
            max_days_old = int(sys.argv[3])
            target_state = sys.argv[4]
            user_email = sys.argv[5]
        else:
            # Fallback to config.json
            print("ℹ️ CLI arguments not provided. Falling back to config.json")
            with open("config.json", "r") as f:
                config = json.load(f)
            search_terms_str = ",".join(config["search_terms"])
            results_wanted = config["results_wanted"]
            max_days_old = config["max_days_old"]
            target_state = config["target_state"]
            user_email = config["user_email"]

        search_terms = [term.strip() for term in search_terms_str.split(",")]
        safe_email = sanitize_email(user_email)
        output_filename = f"jobspy_output_dynamic_{safe_email}.csv"

        jobs = scrape_jobs(search_terms, results_wanted, max_days_old, target_state)
        save_jobs_to_csv(jobs, output_filename)

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)
