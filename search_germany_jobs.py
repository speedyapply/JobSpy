"""
JobSpy script to search for IT/Software Engineering jobs in Germany.

This script searches for jobs in the following areas:
- Software Development
- Software Engineering
- System Engineering
- DevOps
- Site Reliability Engineering (SRE)
- And related IT fields

Priority is given to Berlin-based jobs, with broader Germany search included.
Jobs from the last week are filtered.
"""

import csv
from datetime import datetime
from jobspy import scrape_jobs


def search_germany_it_jobs():
    """
    Search for IT and Software Engineering jobs in Germany.
    Prioritizes Berlin-based jobs first, then searches Germany overall.
    """

    # Define search terms for IT/Software related positions
    search_terms = [
        "Software Engineer",
        "Software Developer",
        "DevOps Engineer",
        "Site Reliability Engineer",
        "System Engineer",
        "Backend Developer",
        "Full Stack Developer",
        "Python Developer",
        "Java Developer",
    ]

    # Job boards to search
    sites = ["indeed", "linkedin", "google"]

    # Hours in a week
    hours_old = 24 * 7  # 7 days (1 week)

    all_jobs = []

    print("=" * 80)
    print("Searching for IT/Software Engineering Jobs in Germany")
    print("=" * 80)
    print(f"Time filter: Jobs posted in the last {hours_old // 24} days")
    print(f"Job boards: {', '.join(sites)}")
    print(f"Locations: Berlin (priority), Germany (general)")
    print("=" * 80)
    print()

    # First, search for Berlin-specific jobs
    print("Step 1: Searching for jobs in Berlin...")
    print("-" * 80)

    for search_term in search_terms:
        print(f"  Searching: {search_term} in Berlin...")
        try:
            jobs = scrape_jobs(
                site_name=sites,
                search_term=search_term,
                location="Berlin, Germany",
                results_wanted=20,
                hours_old=hours_old,
                country_indeed="Germany",
                verbose=1,
            )
            if not jobs.empty:
                print(f"    Found {len(jobs)} jobs for '{search_term}' in Berlin")
                all_jobs.append(jobs)
            else:
                print(f"    No jobs found for '{search_term}' in Berlin")
        except Exception as e:
            print(f"    Error searching '{search_term}' in Berlin: {str(e)}")

    print()
    print("Step 2: Searching for jobs in Germany (general)...")
    print("-" * 80)

    # Then, search for Germany-wide jobs
    for search_term in search_terms:
        print(f"  Searching: {search_term} in Germany...")
        try:
            jobs = scrape_jobs(
                site_name=sites,
                search_term=search_term,
                location="Germany",
                results_wanted=20,
                hours_old=hours_old,
                country_indeed="Germany",
                verbose=1,
            )
            if not jobs.empty:
                print(f"    Found {len(jobs)} jobs for '{search_term}' in Germany")
                all_jobs.append(jobs)
            else:
                print(f"    No jobs found for '{search_term}' in Germany")
        except Exception as e:
            print(f"    Error searching '{search_term}' in Germany: {str(e)}")

    print()
    print("=" * 80)

    # Combine all results
    if all_jobs:
        import pandas as pd

        combined_jobs = pd.concat(all_jobs, ignore_index=True)

        # Remove duplicates based on job_url
        combined_jobs = combined_jobs.drop_duplicates(subset=["job_url"], keep="first")

        # Sort by location to prioritize Berlin jobs
        combined_jobs["is_berlin"] = combined_jobs["location"].str.contains(
            "Berlin", case=False, na=False
        )
        combined_jobs = combined_jobs.sort_values(
            by=["is_berlin", "date_posted"], ascending=[False, False]
        ).reset_index(drop=True)

        # Drop the temporary is_berlin column
        combined_jobs = combined_jobs.drop(columns=["is_berlin"])

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"germany_it_jobs_{timestamp}.csv"

        # Define columns to include in CSV output (ensure title is included)
        csv_columns = [
            "title",
            "company",
            "location",
            "job_type",
            "site",
            "date_posted",
            "job_url",
            "job_url_direct",
            "description",
            "is_remote",
            "salary_source",
            "interval",
            "min_amount",
            "max_amount",
            "currency",
            "company_industry",
            "company_url",
            "job_level",
            "job_function",
        ]
        # Filter to only columns that exist in the dataframe
        columns_to_save = [col for col in csv_columns if col in combined_jobs.columns]

        # Save to CSV with selected columns
        combined_jobs[columns_to_save].to_csv(
            output_file, quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False
        )

        print(f"Total jobs found: {len(combined_jobs)}")
        print(f"Results saved to: {output_file}")
        print(f"Columns saved: {', '.join(columns_to_save)}")
        print()
        print("Sample of results (first 5 jobs):")
        print("-" * 80)

        # Display sample results
        display_columns = [
            "title",
            "company",
            "location",
            "job_type",
            "site",
            "date_posted",
        ]
        available_columns = [
            col for col in display_columns if col in combined_jobs.columns
        ]
        print(combined_jobs[available_columns].head(5).to_string(index=False))

        print()
        print("=" * 80)

        return combined_jobs
    else:
        print("No jobs found matching the search criteria.")
        return None


if __name__ == "__main__":
    results = search_germany_it_jobs()

    if results is not None:
        print(f"\n✓ Successfully completed job search!")
        print(f"  Total unique jobs found: {len(results)}")
    else:
        print("\n✗ No jobs found. Try adjusting search parameters.")
