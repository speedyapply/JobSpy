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
    return email.replace("@", "_at_").replace(".", "_")

def load_config_file(email=None):
    if email:
        safe_email = sanitize_email(email)
        config_path = os.path.join("configs", f"config_{safe_email}.json")
        if os.path.exists(config_path):
            print(f"📂 Loading config for {email} → {config_path}")
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f), safe_email
        else:
            raise FileNotFoundError(f"❌ Config for {email} not found at {config_path}")
    else:
        raise ValueError("❌ Email must be passed as argument")

def scrape_jobs(search_terms, results_wanted, max_days_old, target_state):
    all_jobs = []
    today = datetime.date.today()
    print(f"\n🔍 Scraping jobs for: {search_terms}")

    for term in search_terms:
        for source_name, source_class in sources.items():
            print(f"🚀 Scraping '{term}' from {source_name}...")
            scraper = source_class()
            criteria = ScraperInput(site_type=[source_name], search_term=term, results_wanted=results_wanted)

            try:
                response = scraper.scrape(criteria)
            except Exception as e:
                print(f"❌ Error scraping {source_name}: {e}")
                continue

            for job in response.jobs:
                city = job.location.city.strip() if job.location.city else "Unknown"
                state = job.location.state.strip().upper() if job.location.state else "Unknown"
                country = str(job.location.country) if job.location.country else "Unknown"

                if not any(t.lower() in job.title.lower() for t in search_terms):
                    continue

                if job.date_posted and (today - job.date_posted).days <= max_days_old:
                    if state == target_state or job.is_remote:
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
                            "Location City": city,
                            "Location State": state,
                            "Location Country": country,
                            "Job URL": job.job_url,
                            "Job Description": job.description.replace(",", "") if job.description else "No description available",
                            "Job Source": source_name
                        })
    print(f"✅ {len(all_jobs)} jobs matched.")
    return all_jobs

def save_jobs_to_csv(jobs, output_path):
    if not jobs:
        print("⚠️ No jobs found.")
        return

    fieldnames = [
        "Job ID", "Job Title (Primary)", "Company Name", "Industry",
        "Experience Level", "Job Type", "Is Remote", "Currency",
        "Salary Min", "Salary Max", "Date Posted", "Location City",
        "Location State", "Location Country", "Job URL", "Job Description",
        "Job Source"
    ]

    header = "|~|".join(fieldnames)
    rows = [header]

    for job in jobs:
        row = []
        for field in fieldnames:
            value = str(job.get(field, "Not Provided")).replace(",", "").strip()
            row.append(value if value else "Not Provided")
        rows.append("|~|".join(row))

    output = ",".join(rows)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"💾 Saved output to: {output_path}")

# MAIN
if __name__ == "__main__":
    try:
        user_email = sys.argv[1] if len(sys.argv) >= 2 else None
        config, safe_email = load_config_file(user_email)

        job_data = scrape_jobs(
            search_terms=config["search_terms"],
            results_wanted=config["results_wanted"],
            max_days_old=config["max_days_old"],
            target_state=config["target_state"]
        )

        output_file = f"outputs/jobspy_output_{safe_email}.csv"
        save_jobs_to_csv(job_data, output_file)

    except Exception as e:
        print(f"❌ Fatal Error: {e}")
        sys.exit(1)
