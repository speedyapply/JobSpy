from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple

import pandas as pd

from jobspy.bayt import BaytScraper
from jobspy.bdjobs import BDJobs
from jobspy.glassdoor import Glassdoor
from jobspy.google import Google
from jobspy.indeed import Indeed
from jobspy.linkedin import LinkedIn
from jobspy.naukri import Naukri
from jobspy.model import JobType, Location, JobResponse, Country
from jobspy.model import SalarySource, ScraperInput, Site
from jobspy.util import (
    set_logger_level,
    extract_salary,
    create_logger,
    get_enum_from_value,
    map_str_to_site,
    convert_to_annual,
    desired_order,
)
from jobspy.ziprecruiter import ZipRecruiter


# Update the SCRAPER_MAPPING dictionary in the scrape_jobs function

def scrape_jobs(
    site_name: str | list[str] | Site | list[Site] | None = None,
    search_term: str | None = None,
    google_search_term: str | None = None,
    location: str | None = None,
    distance: int | None = 50,
    is_remote: bool = False,
    job_type: str | None = None,
    easy_apply: bool | None = None,
    results_wanted: int = 15,
    country_indeed: str = "usa",
    proxies: list[str] | str | None = None,
    ca_cert: str | None = None,
    description_format: str = "markdown",
    linkedin_fetch_description: bool | None = False,
    linkedin_company_ids: list[int] | None = None,
    offset: int | None = 0,
    hours_old: int = None,
    enforce_annual_salary: bool = False,
    verbose: int = 0,
    user_agent: str = None,
    **kwargs,
) -> pd.DataFrame:
    """
    Scrape job postings from multiple job boards concurrently.

    This is the main entry point for JobSpy. It searches specified job boards
    in parallel and returns aggregated results as a pandas DataFrame.

    Args:
        site_name: Job board(s) to search. Options: "linkedin", "indeed",
            "zip_recruiter", "glassdoor", "google", "bayt", "naukri".
            Can be a single string, list of strings, or Site enum(s).
            Default: all supported sites.

        search_term: Job title, keywords, or skills to search for.
            Supports Boolean operators for Indeed (AND, OR, -, "exact match").
            Example: '"software engineer" python -junior'

        google_search_term: Custom search term specifically for Google Jobs.
            Use exact syntax from Google Jobs search box for best results.

        location: Geographic location (city, state/province, country) or "Remote".
            Examples: "San Francisco, CA", "New York, NY", "Remote", "London, UK"

        distance: Search radius in miles from location. Default: 50.

        is_remote: If True, filter for remote jobs only. Default: False.

        job_type: Filter by employment type. Options: "fulltime", "parttime",
            "internship", "contract". Default: None (all types).

        easy_apply: Filter for easy apply jobs (site-hosted applications).
            Note: LinkedIn easy apply filter may not work reliably.

        results_wanted: Number of job results to retrieve per site. Default: 15.
            Max ~1000 per search due to job board limitations.

        country_indeed: Country code for Indeed/Glassdoor searches.
            Default: "usa". See README for full list of supported countries.

        proxies: List of proxy servers for avoiding rate limits.
            Format: ["user:pass@host:port", "host:port", "localhost"].
            Recommended for LinkedIn scraping.

        ca_cert: Path to CA certificate file for proxy SSL verification.

        description_format: Format for job descriptions. Options: "markdown", "html".
            Default: "markdown".

        linkedin_fetch_description: If True, fetch full descriptions for LinkedIn
            jobs. Slower but provides more detail. Default: False.

        linkedin_company_ids: List of LinkedIn company IDs to search.
            Useful for targeting specific companies on LinkedIn.

        offset: Start search from this result number. Default: 0.
            Useful for pagination through large result sets.

        hours_old: Filter jobs posted within the last N hours.
            Examples: 24 (last day), 72 (last 3 days), 168 (last week).

        enforce_annual_salary: If True, convert all salaries to annual.
            Default: False.

        verbose: Logging verbosity. 0=errors only, 1=warnings, 2=all. Default: 0.

    Returns:
        pd.DataFrame: DataFrame containing job postings with columns:
            - site: Source job board
            - title: Job title
            - company: Company name
            - location: Job location
            - job_type: Employment type (fulltime, parttime, etc.)
            - min_amount, max_amount: Salary range
            - interval: Salary period (yearly, hourly, etc.)
            - currency: Salary currency
            - date_posted: When job was posted
            - job_url: URL to job posting
            - description: Job description (markdown format)
            - is_remote: Whether job is remote
            - company_url: Company website
            - And additional site-specific fields

    Example:
        >>> from jobspy import scrape_jobs
        >>> import json
        >>>
        >>> # Basic search
        >>> jobs = scrape_jobs(
        ...     site_name=["indeed", "linkedin"],
        ...     search_term="python developer",
        ...     location="San Francisco, CA",
        ...     results_wanted=10
        ... )
        >>> print(f"Found {len(jobs)} jobs")
        >>>
        >>> # Convert to JSON for LLM processing
        >>> result = jobs.to_dict(orient="records")
        >>> print(json.dumps(result, indent=2, default=str))

    Notes:
        - Indeed is recommended as primary source (no rate limiting)
        - LinkedIn requires proxies for sustained use (rate limiting)
        - Results are sorted by site and date_posted (newest first)
        - Empty DataFrame returned if no jobs found

    See Also:
        - CHATGPT_GUIDE.md for LLM integration examples
        - tool_manifest.json for machine-readable API documentation
        - examples/ directory for usage patterns
    """
    SCRAPER_MAPPING = {
        Site.LINKEDIN: LinkedIn,
        Site.INDEED: Indeed,
        Site.ZIP_RECRUITER: ZipRecruiter,
        Site.GLASSDOOR: Glassdoor,
        Site.GOOGLE: Google,
        Site.BAYT: BaytScraper,
        Site.NAUKRI: Naukri,
        Site.BDJOBS: BDJobs,  # Add BDJobs to the scraper mapping
    }
    set_logger_level(verbose)
    job_type = get_enum_from_value(job_type) if job_type else None

    def get_site_type():
        site_types = list(Site)
        if isinstance(site_name, str):
            site_types = [map_str_to_site(site_name)]
        elif isinstance(site_name, Site):
            site_types = [site_name]
        elif isinstance(site_name, list):
            site_types = [
                map_str_to_site(site) if isinstance(site, str) else site
                for site in site_name
            ]
        return site_types

    country_enum = Country.from_string(country_indeed)

    scraper_input = ScraperInput(
        site_type=get_site_type(),
        country=country_enum,
        search_term=search_term,
        google_search_term=google_search_term,
        location=location,
        distance=distance,
        is_remote=is_remote,
        job_type=job_type,
        easy_apply=easy_apply,
        description_format=description_format,
        linkedin_fetch_description=linkedin_fetch_description,
        results_wanted=results_wanted,
        linkedin_company_ids=linkedin_company_ids,
        offset=offset,
        hours_old=hours_old,
    )

    def scrape_site(site: Site) -> Tuple[str, JobResponse]:
        scraper_class = SCRAPER_MAPPING[site]
        scraper = scraper_class(proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)
        scraped_data: JobResponse = scraper.scrape(scraper_input)
        cap_name = site.value.capitalize()
        site_name = "ZipRecruiter" if cap_name == "Zip_recruiter" else cap_name
        site_name = "LinkedIn" if cap_name == "Linkedin" else cap_name
        create_logger(site_name).info(f"finished scraping")
        return site.value, scraped_data

    site_to_jobs_dict = {}

    def worker(site):
        site_val, scraped_info = scrape_site(site)
        return site_val, scraped_info

    with ThreadPoolExecutor() as executor:
        future_to_site = {
            executor.submit(worker, site): site for site in scraper_input.site_type
        }

        for future in as_completed(future_to_site):
            site_value, scraped_data = future.result()
            site_to_jobs_dict[site_value] = scraped_data

    jobs_dfs: list[pd.DataFrame] = []

    for site, job_response in site_to_jobs_dict.items():
        for job in job_response.jobs:
            job_data = job.dict()
            job_url = job_data["job_url"]
            job_data["site"] = site
            job_data["company"] = job_data["company_name"]
            job_data["job_type"] = (
                ", ".join(job_type.value[0] for job_type in job_data["job_type"])
                if job_data["job_type"]
                else None
            )
            job_data["emails"] = (
                ", ".join(job_data["emails"]) if job_data["emails"] else None
            )
            if job_data["location"]:
                job_data["location"] = Location(
                    **job_data["location"]
                ).display_location()

            # Handle compensation
            compensation_obj = job_data.get("compensation")
            if compensation_obj and isinstance(compensation_obj, dict):
                job_data["interval"] = (
                    compensation_obj.get("interval").value
                    if compensation_obj.get("interval")
                    else None
                )
                job_data["min_amount"] = compensation_obj.get("min_amount")
                job_data["max_amount"] = compensation_obj.get("max_amount")
                job_data["currency"] = compensation_obj.get("currency", "USD")
                job_data["salary_source"] = SalarySource.DIRECT_DATA.value
                if enforce_annual_salary and (
                    job_data["interval"]
                    and job_data["interval"] != "yearly"
                    and job_data["min_amount"]
                    and job_data["max_amount"]
                ):
                    convert_to_annual(job_data)
            else:
                if country_enum == Country.USA:
                    (
                        job_data["interval"],
                        job_data["min_amount"],
                        job_data["max_amount"],
                        job_data["currency"],
                    ) = extract_salary(
                        job_data["description"],
                        enforce_annual_salary=enforce_annual_salary,
                    )
                    job_data["salary_source"] = SalarySource.DESCRIPTION.value

            job_data["salary_source"] = (
                job_data["salary_source"]
                if "min_amount" in job_data and job_data["min_amount"]
                else None
            )

            #naukri-specific fields
            job_data["skills"] = (
                ", ".join(job_data["skills"]) if job_data["skills"] else None
            )
            job_data["experience_range"] = job_data.get("experience_range")
            job_data["company_rating"] = job_data.get("company_rating")
            job_data["company_reviews_count"] = job_data.get("company_reviews_count")
            job_data["vacancy_count"] = job_data.get("vacancy_count")
            job_data["work_from_home_type"] = job_data.get("work_from_home_type")

            job_df = pd.DataFrame([job_data])
            jobs_dfs.append(job_df)

    if jobs_dfs:
        # Step 1: Filter out all-NA columns from each DataFrame before concatenation
        filtered_dfs = [df.dropna(axis=1, how="all") for df in jobs_dfs]

        # Step 2: Concatenate the filtered DataFrames
        jobs_df = pd.concat(filtered_dfs, ignore_index=True)

        # Step 3: Ensure all desired columns are present, adding missing ones as empty
        for column in desired_order:
            if column not in jobs_df.columns:
                jobs_df[column] = None  # Add missing columns as empty

        # Reorder the DataFrame according to the desired order
        jobs_df = jobs_df[desired_order]

        # Step 4: Sort the DataFrame as required
        return jobs_df.sort_values(
            by=["site", "date_posted"], ascending=[True, False]
        ).reset_index(drop=True)
    else:
        return pd.DataFrame()


# Add BDJobs to __all__
__all__ = [
    "BDJobs",
]