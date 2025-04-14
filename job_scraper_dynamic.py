import csv
import datetime
import json
import os
from jobspy.google import Google
from jobspy.linkedin import LinkedIn
from jobspy.indeed import Indeed
from jobspy.model import ScraperInput

# --------------------------------------------------------
# Step 1: Load Configuration
# --------------------------------------------------------
def load_config(config_file="config.json"):
    """
    Reads the configuration from a JSON file.
    If the file does not exist, returns a default configuration.
    """
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            config = json.load(f)
        return config
    else:
        # Default configuration if no config file is found.
        return {
            "search_terms": ["Automation Engineer", "CRM Manager", "Project Manager", "POS", "Microsoft Power", "IT Support"],
            "results_wanted": 100,
            "max_days_old": 2,
            "target_state": "NY",
            "user_email": ""
        }

# Load the config
config = load_config()

# Assign configuration values to variables.
search_terms = config.get("search_terms", [])
results_wanted = config.get("results_wanted", 100)
max_days_old = config.get("max_days_old", 2)
target_state = config.get("target_state", "NY")
user_email = config.get("user_email", "")

# --------------------------------------------------------
# Step 2: Define Job Sources
# --------------------------------------------------------
sources = {
    "google": Google,
    "linkedin": LinkedIn,
    "indeed": Indeed,
}

# --------------------------------------------------------
# Step 3: Scrape Jobs Based on the Dynamic Config
# --------------------------------------------------------
def scrape_jobs(search_terms, results_wanted, max_days_old, target_state):
    """Scrape jobs from multiple sources and filter by state."""
    all_jobs = []
    today = datetime.date.today()
    
    print("\n🔎 DEBUG: Fetching jobs for search terms:", search_terms)

    for search_term in search_terms:
        for source_name, source_class in sources.items():
            print(f"\n🚀 Scraping '{search_term}' from {source_name}...")
            scraper = source_class()
            search_criteria = ScraperInput(
                site_type=[source_name],
                search_term=search_term,
                results_wanted=results_wanted,
            )
            job_response = scraper.scrape(search_criteria)

            for job in job_response.jobs:
                # Normalize location fields safely.
                location_city = job.location.city.strip() if job.location and job.location.city else "Unknown"
                location_state = job.location.state.strip().upper() if job.location and job.location.state else "Unknown"
                location_country = str(job.location.country) if job.location and job.location.country else "Unknown"

                # Debug print
                print(f"📍 Fetched Job: {job.title} - {location_city}, {location_state}, {location_country}")

                # Only include jobs whose title contains one of the search terms.
                if not any(term.lower() in job.title.lower() for term in search_terms):
                    print(f"🚫 Excluding: {job.title} (Does not match {search_terms})")
                    continue

                # Only include jobs that are recent.
                if job.date_posted and (today - job.date_posted).days <= max_days_old:
                    # Accept the job if it's in the target state or if it is remote.
                    if location_state == target_state or job.is_remote:
                        print(f"✅ MATCH: {job.title} - {location_city}, {location_state} (Posted {job.date_posted})")
                        job_record = {
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
                            "Job Description": job.description.replace(",", "") if job.description else "No description available",
                            "Job Source": source_name
                        }
                        # Optionally tag the record with the user email if provided.
                        if user_email:
                            job_record["User Email"] = user_email
                        all_jobs.append(job_record)
                    else:
                        print(f"❌ Ignored (Wrong State): {job.title} - {location_city}, {location_state} (Posted {job.date_posted})")
                else:
                    print(f"⏳ Ignored (Too Old): {job.title} - {location_city}, {location_state} (Posted {job.date_posted})")

    print(f"\n✅ {len(all_jobs)} jobs retrieved in {target_state}")
    return all_jobs

# --------------------------------------------------------
# Step 4: Save the Job Data to a CSV File
# --------------------------------------------------------
def save_jobs_to_csv(jobs, filename="jobspy_output.csv"):
    """
    Saves job data to a CSV file using a custom delimiter.
    Fields within a record are separated by |~|,
    Records are separated by commas,
    All commas in field values are removed,
    Blank fields are replaced with 'Not Provided'.
    """
    if not jobs:
        print("⚠️ No jobs found matching criteria.")
        return

    # Delete any existing file.
    if os.path.exists(filename):
        os.remove(filename)

    fieldnames = [
        "Job ID", "Job Title (Primary)", "Company Name", "Industry",
        "Experience Level", "Job Type", "Is Remote", "Currency",
        "Salary Min", "Salary Max", "Date Posted", "Location City",
        "Location State", "Location Country", "Job URL", "Job Description",
        "Job Source"
    ]

    # Include User Email in header if present in any record.
    if any("User Email" in job for job in jobs):
        fieldnames.insert(0, "User Email")

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

# --------------------------------------------------------
# MAIN EXECUTION
# --------------------------------------------------------
if __name__ == "__main__":
    job_data = scrape_jobs(
        search_terms=search_terms,
        results_wanted=results_wanted,
        max_days_old=max_days_old,
        target_state=target_state
    )
    save_jobs_to_csv(job_data)
