"""
Basic Job Search Example

This example demonstrates a simple job search across multiple job boards.
Perfect for ChatGPT to use as a reference for basic queries.

Usage:
    python examples/basic_search.py
"""

from jobspy import scrape_jobs
import json

def basic_job_search():
    """
    Search for software engineer jobs in San Francisco.
    Returns results as both DataFrame and JSON for flexibility.
    """
    jobs = scrape_jobs(
        site_name=["indeed", "linkedin"],
        search_term="software engineer",
        location="San Francisco, CA",
        results_wanted=10,
        hours_old=72,  # Jobs posted in last 3 days
        country_indeed="usa",
        verbose=0  # Suppress logging
    )

    print(f"Found {len(jobs)} jobs\n")

    # Display as table
    print("=== Results Preview ===")
    print(jobs[["site", "title", "company", "location"]].head(5).to_string(index=False))

    # Convert to JSON for LLM consumption
    jobs_json = jobs.to_dict(orient="records")

    return {
        "success": True,
        "count": len(jobs),
        "jobs": jobs_json
    }


if __name__ == "__main__":
    result = basic_job_search()
    print(f"\n=== JSON Output ===")
    print(json.dumps(result, indent=2, default=str)[:2000] + "...")
