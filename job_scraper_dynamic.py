import csv, datetime, os, sys, json
from jobspy.google import Google
from jobspy.linkedin import LinkedIn
from jobspy.indeed import Indeed
from jobspy.model import ScraperInput

sources = {
    "google": Google,
    "linkedin": LinkedIn,
    "indeed": Indeed,
}

def sanitize_email(email):
    return email.replace("@", "_at_").replace(".", "_")

def load_config(email):
    safe_email = sanitize_email(email)
    config_path = os.path.join("configs", f"config_{safe_email}.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"❌ Config for {email} not found at {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f), safe_email

def scrape_jobs(search_terms, results_wanted, max_days_old, target_state):
    today = datetime.date.today()
    all_jobs = []

    for term in search_terms:
        for source, Scraper in sources.items():
            print(f"🔍 Scraping {term} from {source}")
            scraper = Scraper()
            try:
                jobs = scraper.scrape(ScraperInput(
                    site_type=[source],
                    search_term=term,
                    results_wanted=results_wanted
                )).jobs
            except Exception as e:
                print(f"⚠️ {source} error: {e}")
                continue

            for job in jobs:
                if job.date_posted and (today - job.date_posted).days <= max_days_old:
                    if target_state == (job.location.state or "").upper() or job.is_remote:
                        if any(term.lower() in job.title.lower() for term in search_terms):
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
                                "Date Posted": job.date_posted.strftime("%Y-%m-%d"),
                                "Location City": job.location.city or "Unknown",
                                "Location State": (job.location.state or "Unknown").upper(),
                                "Location Country": job.location.country or "Unknown",
                                "Job URL": job.job_url,
                                "Job Description": job.description.replace(",", "") if job.description else "No description",
                                "Job Source": source
                            })
    print(f"✅ Found {len(all_jobs)} jobs")
    return all_jobs

def save_to_csv(jobs, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fieldnames = [
        "Job ID", "Job Title (Primary)", "Company Name", "Industry",
        "Experience Level", "Job Type", "Is Remote", "Currency",
        "Salary Min", "Salary Max", "Date Posted", "Location City",
        "Location State", "Location Country", "Job URL", "Job Description", "Job Source"
    ]
    header = "|~|".join(fieldnames)
    rows = [header] + ["|~|".join(str(job.get(col, "Not Provided")).replace(",", "").strip() for col in fieldnames) for job in jobs]
    with open(path, "w", encoding="utf-8") as f:
        f.write(",".join(rows))
    print(f"💾 Saved output to: {path}")

if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("❌ Usage: python job_scraper_dynamic.py <user_email> <run_id>")

        user_email, run_id = sys.argv[1], sys.argv[2]
        config, safe_email = load_config(user_email)
        jobs = scrape_jobs(config["search_terms"], config["results_wanted"], config["max_days_old"], config["target_state"])
        save_to_csv(jobs, f"outputs/jobspy_output_{safe_email}_{run_id}.csv")

    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
