"""
Federal Contractor Job Search Example

This example demonstrates searching for jobs at federal contractors and
defense-related positions - useful for CIS labor category mapping and
BD intelligence gathering.

Usage:
    python examples/federal_contractor_search.py
"""

from jobspy import scrape_jobs
import json


def search_federal_contractor_jobs():
    """
    Search for jobs at major federal contractors and defense companies.
    Useful for BD teams tracking competitor hiring and market intelligence.
    """

    # Search terms relevant to federal/defense contracting
    search_queries = [
        {
            "term": "security clearance",
            "location": "Washington, DC",
            "description": "Cleared positions in DC area"
        },
        {
            "term": "program manager government",
            "location": "Virginia",
            "description": "Government PM roles"
        },
        {
            "term": "systems engineer TS/SCI",
            "location": "Remote",
            "description": "Cleared systems engineers"
        }
    ]

    all_results = []

    for query in search_queries:
        print(f"\nSearching: {query['description']}...")

        jobs = scrape_jobs(
            site_name=["indeed", "linkedin"],
            search_term=query["term"],
            location=query["location"],
            results_wanted=15,
            hours_old=168,  # Last week
            country_indeed="usa",
            linkedin_fetch_description=False,  # Set True for full descriptions
            verbose=0
        )

        # Add query context to results
        for _, job in jobs.iterrows():
            job_dict = job.to_dict()
            job_dict["search_query"] = query["term"]
            job_dict["query_location"] = query["location"]
            all_results.append(job_dict)

        print(f"  Found {len(jobs)} jobs")

    # Summary by company (useful for BD intelligence)
    companies = {}
    for job in all_results:
        company = job.get("company", "Unknown")
        if company not in companies:
            companies[company] = {"count": 0, "roles": []}
        companies[company]["count"] += 1
        companies[company]["roles"].append(job.get("title", "N/A"))

    # Sort by hiring volume
    top_hiring = sorted(companies.items(), key=lambda x: x[1]["count"], reverse=True)[:10]

    print("\n=== Top Hiring Companies ===")
    for company, data in top_hiring:
        print(f"{company}: {data['count']} openings")

    return {
        "success": True,
        "total_jobs": len(all_results),
        "companies_found": len(companies),
        "top_hiring": dict(top_hiring),
        "jobs": all_results
    }


def search_competitor_staffing_companies():
    """
    Search for jobs posted by competitor staffing companies.
    These are the staffing agencies you provided as competitors.
    """

    # Competitor staffing companies to monitor
    competitors = [
        "Insight Global",
        "TEKsystems",
        "Apex Systems",
        "Belcan",
        "GDIT",
        "Booz Allen Hamilton",
        "Leidos",
        "SAIC",
        "ManTech",
        "Peraton"
    ]

    all_results = []

    for company in competitors:
        print(f"\nSearching jobs at: {company}...")

        # Search for company name in job postings
        jobs = scrape_jobs(
            site_name=["indeed"],
            search_term=f'"{company}"',  # Exact company match
            location="",  # All locations
            results_wanted=20,
            country_indeed="usa",
            verbose=0
        )

        for _, job in jobs.iterrows():
            job_dict = job.to_dict()
            job_dict["target_company"] = company
            all_results.append(job_dict)

        print(f"  Found {len(jobs)} jobs")

    return {
        "success": True,
        "total_jobs": len(all_results),
        "competitors_searched": len(competitors),
        "jobs": all_results
    }


if __name__ == "__main__":
    print("=== Federal Contractor Job Search ===")
    result = search_federal_contractor_jobs()

    print("\n" + "="*50)
    print("\n=== Competitor Staffing Company Search ===")
    competitor_result = search_competitor_staffing_companies()

    # Save results to JSON files
    with open("federal_jobs.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    with open("competitor_jobs.json", "w") as f:
        json.dump(competitor_result, f, indent=2, default=str)

    print("\nResults saved to federal_jobs.json and competitor_jobs.json")
