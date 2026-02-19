"""
Business Development Intelligence Search

This example demonstrates using JobSpy for BD intelligence gathering:
- Identifying companies with high hiring activity (growth signals)
- Monitoring competitor hiring patterns
- Finding opportunities based on job postings

Perfect for ChatGPT-assisted BD research and lead scoring.

Usage:
    python examples/bd_intelligence_search.py
"""

from jobspy import scrape_jobs
from collections import defaultdict
from datetime import datetime
import json


def analyze_hiring_trends(
    search_term: str,
    location: str = "",
    results_wanted: int = 100
) -> dict:
    """
    Analyze hiring trends for a given search term.
    Useful for identifying companies with growth signals.

    Returns analysis including:
    - Companies sorted by number of openings
    - Job type distribution
    - Salary ranges
    - Remote vs on-site breakdown
    """

    jobs_df = scrape_jobs(
        site_name=["indeed", "linkedin"],
        search_term=search_term,
        location=location,
        results_wanted=results_wanted,
        country_indeed="usa",
        verbose=0
    )

    if jobs_df.empty:
        return {"success": False, "error": "No jobs found", "count": 0}

    # Company analysis
    company_counts = defaultdict(lambda: {"count": 0, "titles": [], "locations": set()})
    for _, job in jobs_df.iterrows():
        company = job.get("company", "Unknown")
        company_counts[company]["count"] += 1
        company_counts[company]["titles"].append(job.get("title", "N/A"))
        if job.get("location"):
            company_counts[company]["locations"].add(job["location"])

    # Sort by hiring volume
    top_companies = sorted(
        [
            {
                "company": k,
                "openings": v["count"],
                "sample_roles": list(set(v["titles"]))[:5],
                "locations": list(v["locations"])
            }
            for k, v in company_counts.items()
        ],
        key=lambda x: x["openings"],
        reverse=True
    )[:20]

    # Job type distribution
    job_types = jobs_df["job_type"].value_counts().to_dict() if "job_type" in jobs_df else {}

    # Remote analysis
    remote_count = jobs_df["is_remote"].sum() if "is_remote" in jobs_df else 0

    # Salary analysis
    salary_data = []
    for _, job in jobs_df.iterrows():
        if job.get("min_amount") and job.get("max_amount"):
            salary_data.append({
                "min": job["min_amount"],
                "max": job["max_amount"],
                "interval": job.get("interval", "yearly")
            })

    return {
        "success": True,
        "count": len(jobs_df),
        "analysis_date": datetime.now().isoformat(),
        "search_params": {
            "search_term": search_term,
            "location": location
        },
        "top_hiring_companies": top_companies,
        "job_type_distribution": job_types,
        "remote_positions": {
            "count": int(remote_count),
            "percentage": round(remote_count / len(jobs_df) * 100, 1) if len(jobs_df) > 0 else 0
        },
        "salary_data_points": len(salary_data),
        "unique_companies": len(company_counts)
    }


def monitor_target_accounts(target_companies: list, search_term: str = "") -> dict:
    """
    Monitor specific target accounts for their job postings.
    Useful for BD teams tracking key prospects.

    Args:
        target_companies: List of company names to monitor
        search_term: Optional filter for specific roles

    Returns:
        Analysis of each target company's hiring activity
    """

    results = []

    for company in target_companies:
        # Combine company name with search term for more targeted results
        query = f'"{company}" {search_term}'.strip()

        jobs_df = scrape_jobs(
            site_name=["indeed"],
            search_term=query,
            results_wanted=30,
            country_indeed="usa",
            verbose=0
        )

        # Filter to ensure company match
        company_jobs = jobs_df[
            jobs_df["company"].str.contains(company, case=False, na=False)
        ] if not jobs_df.empty else jobs_df

        if not company_jobs.empty:
            roles = company_jobs["title"].tolist()
            locations = company_jobs["location"].unique().tolist()

            results.append({
                "company": company,
                "openings_found": len(company_jobs),
                "sample_roles": roles[:10],
                "hiring_locations": locations,
                "growth_signal": "HIGH" if len(company_jobs) > 10 else "MEDIUM" if len(company_jobs) > 3 else "LOW"
            })
        else:
            results.append({
                "company": company,
                "openings_found": 0,
                "growth_signal": "NONE"
            })

    return {
        "success": True,
        "monitored_companies": len(target_companies),
        "companies_with_openings": sum(1 for r in results if r["openings_found"] > 0),
        "results": results
    }


def find_opportunities_by_keywords(keywords: list, location: str = "") -> dict:
    """
    Search for BD opportunities based on specific keywords.
    Useful for finding companies with specific needs/projects.

    Args:
        keywords: List of keywords indicating opportunity (e.g., ["cloud migration", "modernization"])
        location: Geographic filter

    Returns:
        Companies and roles matching the keywords
    """

    all_opportunities = []

    for keyword in keywords:
        jobs_df = scrape_jobs(
            site_name=["indeed", "linkedin"],
            search_term=keyword,
            location=location,
            results_wanted=25,
            hours_old=168,  # Last week
            country_indeed="usa",
            verbose=0
        )

        for _, job in jobs_df.iterrows():
            all_opportunities.append({
                "keyword": keyword,
                "company": job.get("company"),
                "title": job.get("title"),
                "location": job.get("location"),
                "job_url": job.get("job_url"),
                "description_preview": str(job.get("description", ""))[:300] if job.get("description") else None
            })

    # Group by company
    company_opportunities = defaultdict(list)
    for opp in all_opportunities:
        company_opportunities[opp["company"]].append(opp)

    # Score companies by keyword coverage
    scored_companies = [
        {
            "company": company,
            "total_matches": len(opps),
            "keywords_matched": list(set(o["keyword"] for o in opps)),
            "opportunities": opps
        }
        for company, opps in company_opportunities.items()
    ]

    scored_companies.sort(key=lambda x: len(x["keywords_matched"]), reverse=True)

    return {
        "success": True,
        "keywords_searched": keywords,
        "total_opportunities": len(all_opportunities),
        "unique_companies": len(company_opportunities),
        "top_opportunities": scored_companies[:15]
    }


if __name__ == "__main__":
    print("=== BD Intelligence Job Analysis ===\n")

    # Example 1: Analyze hiring trends for cloud engineers
    print("1. Analyzing hiring trends for 'cloud engineer'...")
    trends = analyze_hiring_trends("cloud engineer", "Remote", results_wanted=50)
    print(f"   Found {trends['count']} jobs across {trends['unique_companies']} companies")
    print(f"   Top hiring: {[c['company'] for c in trends['top_hiring_companies'][:5]]}")

    # Example 2: Monitor target accounts
    print("\n2. Monitoring target accounts...")
    targets = ["Amazon", "Google", "Microsoft", "Booz Allen", "Leidos"]
    monitor_result = monitor_target_accounts(targets, "engineer")
    for r in monitor_result["results"]:
        print(f"   {r['company']}: {r['openings_found']} openings ({r['growth_signal']} signal)")

    # Example 3: Find opportunities by keywords
    print("\n3. Searching for BD opportunities...")
    opportunity_keywords = ["cloud migration", "digital transformation", "modernization"]
    opportunities = find_opportunities_by_keywords(opportunity_keywords, "DC")
    print(f"   Found {opportunities['total_opportunities']} matches across {opportunities['unique_companies']} companies")

    # Save full results
    full_results = {
        "trends": trends,
        "target_monitoring": monitor_result,
        "opportunities": opportunities
    }

    with open("bd_intelligence_report.json", "w") as f:
        json.dump(full_results, f, indent=2, default=str)

    print("\nFull report saved to bd_intelligence_report.json")
