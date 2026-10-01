"""
JSON Output Example for LLM Integration

This example shows how to get job results in JSON format,
which is ideal for ChatGPT and other LLMs to parse and process.

Usage:
    python examples/json_output_example.py

For ChatGPT:
    When asked to search for jobs, use this pattern to return
    structured JSON that can be easily parsed and analyzed.
"""

from jobspy import scrape_jobs
import json
import sys


def search_jobs_json(
    search_term: str,
    location: str = "",
    sites: list = None,
    results_wanted: int = 15,
    hours_old: int = None,
    remote_only: bool = False,
    job_type: str = None,
    fields: list = None
) -> dict:
    """
    Search for jobs and return results as a JSON-serializable dictionary.

    This function is designed for easy integration with ChatGPT and other LLMs.
    All parameters have sensible defaults and the output is always valid JSON.

    Args:
        search_term: Job title or keywords to search for
        location: Location (city, state) or "Remote" for remote jobs
        sites: List of job sites ["indeed", "linkedin", "glassdoor", etc.]
        results_wanted: Number of results per site (default: 15)
        hours_old: Only jobs posted within N hours (optional)
        remote_only: If True, only return remote jobs
        job_type: Filter by type - "fulltime", "parttime", "contract", "internship"
        fields: List of fields to include in output (optional, returns all if None)

    Returns:
        dict: {
            "success": bool,
            "count": int,
            "search_params": dict,
            "jobs": list[dict]
        }

    Example:
        >>> result = search_jobs_json("python developer", "NYC", results_wanted=5)
        >>> print(result["count"])
        5
        >>> for job in result["jobs"]:
        ...     print(f"{job['title']} at {job['company']}")
    """

    if sites is None:
        sites = ["indeed", "linkedin"]

    # Default fields for LLM consumption (most useful fields)
    default_fields = [
        "site", "title", "company", "location", "job_type",
        "min_amount", "max_amount", "interval", "currency",
        "date_posted", "job_url", "is_remote", "description"
    ]

    output_fields = fields if fields else default_fields

    try:
        jobs_df = scrape_jobs(
            site_name=sites,
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            is_remote=remote_only,
            job_type=job_type,
            country_indeed="usa",
            verbose=0
        )

        # Convert to list of dicts
        jobs_list = jobs_df.to_dict(orient="records")

        # Filter to requested fields
        if fields:
            jobs_list = [
                {k: v for k, v in job.items() if k in output_fields}
                for job in jobs_list
            ]

        return {
            "success": True,
            "count": len(jobs_list),
            "search_params": {
                "search_term": search_term,
                "location": location,
                "sites": sites,
                "results_wanted": results_wanted,
                "hours_old": hours_old,
                "remote_only": remote_only,
                "job_type": job_type
            },
            "jobs": jobs_list
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "count": 0,
            "jobs": []
        }


def print_json_result(result: dict, pretty: bool = True):
    """Print result as JSON to stdout."""
    if pretty:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(json.dumps(result, default=str))


# Example usage patterns for ChatGPT
CHATGPT_EXAMPLES = """
=== ChatGPT Usage Examples ===

1. Basic Search:
   result = search_jobs_json("data scientist", "Boston, MA", results_wanted=10)

2. Remote Jobs Only:
   result = search_jobs_json("software engineer", remote_only=True, results_wanted=20)

3. Recent Contract Jobs:
   result = search_jobs_json("project manager", "DC", job_type="contract", hours_old=24)

4. Multi-Site Search:
   result = search_jobs_json("DevOps", "Seattle",
                            sites=["indeed", "linkedin", "glassdoor"])

5. Specific Fields Only:
   result = search_jobs_json("analyst", fields=["title", "company", "job_url"])

6. Process Results:
   result = search_jobs_json("python developer")
   for job in result["jobs"]:
       print(f"[{job['site']}] {job['title']} at {job['company']}")
       print(f"  URL: {job['job_url']}")
"""


if __name__ == "__main__":
    # Example: Search for Python developers
    print("Searching for Python developer jobs...\n")

    result = search_jobs_json(
        search_term="python developer",
        location="Remote",
        sites=["indeed", "linkedin"],
        results_wanted=5,
        hours_old=72
    )

    print_json_result(result)

    print("\n" + CHATGPT_EXAMPLES)
