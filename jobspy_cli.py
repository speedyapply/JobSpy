#!/usr/bin/env python3
"""
JobSpy CLI - Command-line interface for ChatGPT and LLM integration.

This CLI wrapper enables ChatGPT and other LLMs to invoke JobSpy for job searches
via command-line execution with JSON input/output for easy parsing.

Usage Examples:
    # Basic search
    python jobspy_cli.py --search "software engineer" --location "San Francisco, CA"

    # Search specific sites with JSON output
    python jobspy_cli.py --search "data analyst" --sites indeed,linkedin --format json

    # Full search with all options
    python jobspy_cli.py --search "project manager" --location "Remote" --sites indeed,linkedin,glassdoor --results 25 --hours 48 --format json

    # JSON input mode (for programmatic use)
    echo '{"search_term": "python developer", "location": "NYC"}' | python jobspy_cli.py --json-input
"""

import argparse
import json
import sys
import csv
from io import StringIO
from typing import Optional

try:
    from jobspy import scrape_jobs
except ImportError:
    print(json.dumps({
        "error": "JobSpy not installed. Run: pip install python-jobspy",
        "success": False
    }))
    sys.exit(1)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="JobSpy CLI - Search multiple job boards with one command",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --search "software engineer" --location "NYC"
  %(prog)s --search "data analyst" --sites indeed,linkedin --format json
  %(prog)s --json-input < params.json

Supported Sites:
  indeed, linkedin, zip_recruiter, glassdoor, google, bayt, naukri

Output Formats:
  json    - JSON array of job objects (default for LLM use)
  csv     - CSV formatted output
  table   - Human-readable table format
  summary - Condensed summary with key fields only
        """
    )

    # Search parameters
    parser.add_argument("--search", "-s", type=str, help="Search term/job title")
    parser.add_argument("--location", "-l", type=str, help="Job location (city, state, or 'Remote')")
    parser.add_argument("--sites", type=str, default="indeed,linkedin",
                       help="Comma-separated list of sites to search (default: indeed,linkedin)")
    parser.add_argument("--results", "-n", type=int, default=15,
                       help="Number of results per site (default: 15)")
    parser.add_argument("--hours", type=int, help="Only jobs posted within N hours")
    parser.add_argument("--distance", type=int, default=50, help="Search radius in miles (default: 50)")
    parser.add_argument("--remote", action="store_true", help="Filter for remote jobs only")
    parser.add_argument("--job-type", type=str, choices=["fulltime", "parttime", "internship", "contract"],
                       help="Filter by job type")
    parser.add_argument("--country", type=str, default="usa", help="Country for Indeed/Glassdoor (default: usa)")

    # LinkedIn specific
    parser.add_argument("--linkedin-descriptions", action="store_true",
                       help="Fetch full descriptions for LinkedIn jobs (slower)")
    parser.add_argument("--linkedin-company-ids", type=str,
                       help="Comma-separated LinkedIn company IDs to search")

    # Output options
    parser.add_argument("--format", "-f", type=str, default="json",
                       choices=["json", "csv", "table", "summary"],
                       help="Output format (default: json)")
    parser.add_argument("--output", "-o", type=str, help="Output file path (default: stdout)")
    parser.add_argument("--fields", type=str,
                       help="Comma-separated list of fields to include in output")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    # Advanced options
    parser.add_argument("--proxies", type=str, help="Comma-separated list of proxy servers")
    parser.add_argument("--google-search-term", type=str,
                       help="Custom search term for Google Jobs (use exact Google Jobs syntax)")
    parser.add_argument("--verbose", "-v", type=int, default=0, choices=[0, 1, 2],
                       help="Verbosity level (0=errors, 1=warnings, 2=all)")

    # JSON input mode
    parser.add_argument("--json-input", action="store_true",
                       help="Read search parameters from JSON on stdin")

    # Utility commands
    parser.add_argument("--list-sites", action="store_true", help="List all supported job sites")
    parser.add_argument("--list-countries", action="store_true", help="List supported countries")
    parser.add_argument("--version", action="store_true", help="Show version info")

    return parser.parse_args()


def format_output(jobs_df, format_type: str, fields: Optional[list] = None, pretty: bool = False) -> str:
    """Format job results for output."""
    if jobs_df.empty:
        if format_type == "json":
            return json.dumps({"jobs": [], "count": 0, "success": True})
        return "No jobs found."

    # Filter fields if specified
    if fields:
        available_fields = [f for f in fields if f in jobs_df.columns]
        if available_fields:
            jobs_df = jobs_df[available_fields]

    if format_type == "json":
        # Convert to list of dicts for JSON
        jobs_list = jobs_df.to_dict(orient="records")
        result = {
            "jobs": jobs_list,
            "count": len(jobs_list),
            "success": True
        }
        if pretty:
            return json.dumps(result, indent=2, default=str)
        return json.dumps(result, default=str)

    elif format_type == "csv":
        output = StringIO()
        jobs_df.to_csv(output, index=False, quoting=csv.QUOTE_NONNUMERIC)
        return output.getvalue()

    elif format_type == "table":
        # Simple table format
        key_cols = ["site", "title", "company", "location", "job_url"]
        display_cols = [c for c in key_cols if c in jobs_df.columns]
        return jobs_df[display_cols].to_string(index=False)

    elif format_type == "summary":
        # Condensed summary for quick overview
        summary_lines = [f"Found {len(jobs_df)} jobs:\n"]
        for _, job in jobs_df.iterrows():
            title = job.get("title", "N/A")
            company = job.get("company", "N/A")
            location = job.get("location", "N/A")
            site = job.get("site", "N/A")
            summary_lines.append(f"- [{site}] {title} at {company} ({location})")
        return "\n".join(summary_lines)

    return str(jobs_df)


def run_search(params: dict) -> str:
    """Execute job search with given parameters."""
    try:
        # Parse sites
        sites = params.get("sites", "indeed,linkedin")
        if isinstance(sites, str):
            sites = [s.strip() for s in sites.split(",")]

        # Parse proxies
        proxies = params.get("proxies")
        if isinstance(proxies, str):
            proxies = [p.strip() for p in proxies.split(",")]

        # Parse LinkedIn company IDs
        company_ids = params.get("linkedin_company_ids")
        if isinstance(company_ids, str):
            company_ids = [int(id.strip()) for id in company_ids.split(",")]

        # Execute search
        jobs_df = scrape_jobs(
            site_name=sites,
            search_term=params.get("search_term") or params.get("search"),
            google_search_term=params.get("google_search_term"),
            location=params.get("location"),
            distance=params.get("distance", 50),
            is_remote=params.get("remote", False) or params.get("is_remote", False),
            job_type=params.get("job_type"),
            results_wanted=params.get("results", 15) or params.get("results_wanted", 15),
            hours_old=params.get("hours") or params.get("hours_old"),
            country_indeed=params.get("country", "usa") or params.get("country_indeed", "usa"),
            proxies=proxies,
            linkedin_fetch_description=params.get("linkedin_descriptions", False) or params.get("linkedin_fetch_description", False),
            linkedin_company_ids=company_ids,
            verbose=params.get("verbose", 0),
        )

        # Format output
        format_type = params.get("format", "json")
        fields = params.get("fields")
        if isinstance(fields, str):
            fields = [f.strip() for f in fields.split(",")]

        return format_output(jobs_df, format_type, fields, params.get("pretty", False))

    except Exception as e:
        error_response = {
            "error": str(e),
            "success": False,
            "hint": "Check your search parameters and try again. Use --help for usage info."
        }
        return json.dumps(error_response, indent=2)


def list_sites():
    """List all supported job sites."""
    sites = {
        "indeed": "Indeed.com - Best coverage, no rate limiting",
        "linkedin": "LinkedIn Jobs - Requires proxies for best results",
        "zip_recruiter": "ZipRecruiter - US/Canada only",
        "glassdoor": "Glassdoor - Includes company reviews",
        "google": "Google Jobs - Aggregates from multiple sources",
        "bayt": "Bayt.com - Middle East job board",
        "naukri": "Naukri.com - India job board"
    }
    return json.dumps({"sites": sites, "default": ["indeed", "linkedin"]}, indent=2)


def list_countries():
    """List supported countries for Indeed/Glassdoor."""
    countries = [
        "usa", "uk", "canada", "australia", "germany", "france", "india",
        "netherlands", "spain", "italy", "brazil", "mexico", "japan",
        "singapore", "hong kong", "new zealand", "ireland", "belgium",
        "switzerland", "austria", "poland", "czech republic", "sweden",
        "norway", "denmark", "finland", "portugal", "greece", "turkey",
        "south africa", "united arab emirates", "saudi arabia", "egypt",
        "nigeria", "pakistan", "philippines", "malaysia", "thailand",
        "vietnam", "indonesia", "south korea", "taiwan", "china"
    ]
    return json.dumps({
        "countries": countries,
        "note": "Use exact spelling for country_indeed parameter",
        "glassdoor_supported": ["usa", "uk", "canada", "australia", "germany", "france", "india", "netherlands", "spain", "italy", "brazil", "mexico", "singapore", "hong kong", "new zealand", "ireland", "belgium", "switzerland"]
    }, indent=2)


def main():
    """Main entry point."""
    args = parse_args()

    # Handle utility commands
    if args.version:
        print(json.dumps({"name": "JobSpy CLI", "version": "1.0.0", "library": "python-jobspy"}))
        return

    if args.list_sites:
        print(list_sites())
        return

    if args.list_countries:
        print(list_countries())
        return

    # Handle JSON input mode
    if args.json_input:
        try:
            input_data = sys.stdin.read()
            params = json.loads(input_data)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"Invalid JSON input: {e}", "success": False}))
            sys.exit(1)
    else:
        # Build params from command-line args
        if not args.search:
            print(json.dumps({
                "error": "Search term required. Use --search 'job title' or --json-input",
                "success": False,
                "usage": "python jobspy_cli.py --search 'software engineer' --location 'NYC'"
            }))
            sys.exit(1)

        params = {
            "search_term": args.search,
            "location": args.location,
            "sites": args.sites,
            "results": args.results,
            "hours": args.hours,
            "distance": args.distance,
            "remote": args.remote,
            "job_type": args.job_type,
            "country": args.country,
            "linkedin_descriptions": args.linkedin_descriptions,
            "linkedin_company_ids": args.linkedin_company_ids,
            "google_search_term": args.google_search_term,
            "proxies": args.proxies,
            "verbose": args.verbose,
            "format": args.format,
            "fields": args.fields,
            "pretty": args.pretty,
        }

    # Run search
    result = run_search(params)

    # Output results
    if args.output:
        with open(args.output, "w") as f:
            f.write(result)
        print(json.dumps({"success": True, "output_file": args.output}))
    else:
        print(result)


if __name__ == "__main__":
    main()
