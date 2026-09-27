from jobspy import scrape_jobs

jobs = scrape_jobs(
    site_name=["linkedin"],
    search_term="Software engineer, Information Technology, AI",
    location="Sri Lanka",
    results_wanted=50,
    country_indeed="sri lanka",
    # is_remote=True,
    hours_old=2
)

print(f"Found {len(jobs)} jobs")

print(jobs.head())
