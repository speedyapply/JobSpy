from __future__ import annotations

import difflib
import inspect
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from jobspy.bayt import BaytScraper
from jobspy.bdjobs import BDJobs
from jobspy.glassdoor import Glassdoor
from jobspy.google import Google
from jobspy.indeed import Indeed
from jobspy.linkedin import LinkedIn
from jobspy.naukri import Naukri
from jobspy.model import JobType as JobType
from jobspy.model import Location, JobResponse, Country
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


def scrape_jobs(
    site_name: str | list[str] | Site | list[Site] | None = None,
    search_term: str | None = None,
    google_search_term: str | None = None,
    location: str | None = None,
    distance: int | None = 50,
    is_remote: bool | None = False,
    job_type: str | None = None,
    easy_apply: bool | None = None,
    results_wanted: int | None = 15,
    country_indeed: str | None = "usa",
    proxies: list[str] | str | None = None,
    ca_cert: str | None = None,
    description_format: str | None = "markdown",
    linkedin_fetch_description: bool | None = False,
    linkedin_company_ids: list[int] | None = None,
    offset: int | None = 0,
    hours_old: int | None = None,
    enforce_annual_salary: bool | None = False,
    verbose: int | None = 1,
    user_agent: str | None = None,
    fetch_description: bool | None = False,
    **kwargs,
) -> pd.DataFrame:
    """
    Scrapes job data from job boards concurrently
    :param linkedin_fetch_description: Deprecated since 1.2.0: use fetch_description;
        will be removed in 2.0.
    :return: Pandas DataFrame containing job data
    """
    SCRAPER_MAPPING = {
        Site.LINKEDIN: LinkedIn,
        Site.INDEED: Indeed,
        Site.ZIP_RECRUITER: ZipRecruiter,
        Site.GLASSDOOR: Glassdoor,
        Site.GOOGLE: Google,
        Site.BAYT: BaytScraper,
        Site.NAUKRI: Naukri,
        Site.BDJOBS: BDJobs,
    }
    set_logger_level(verbose)
    if linkedin_fetch_description:
        warnings.warn(
            "linkedin_fetch_description is deprecated; use fetch_description",
            DeprecationWarning,
            stacklevel=2,
        )
    if kwargs:
        known = [
            name
            for name in inspect.signature(scrape_jobs).parameters
            if name not in ("kwargs", "linkedin_fetch_description")
        ]
        unknown = []
        for name in kwargs:
            close = difflib.get_close_matches(name, known, n=1)
            unknown.append(f"{name} (did you mean {close[0]}?)" if close else name)
        warnings.warn(
            f"scrape_jobs ignores unknown arguments: {', '.join(unknown)}",
            FutureWarning,
            stacklevel=2,
        )
    job_type = get_enum_from_value(job_type) if job_type else None

    if isinstance(site_name, (list, tuple, set)):
        sites = site_name
    elif isinstance(site_name, (str, Site)):
        sites = [site_name]
    else:
        sites = [site for site in Site if site != Site.GOOGLE]
    site_type = [map_str_to_site(s) if isinstance(s, str) else s for s in sites]

    is_remote = False if is_remote is None else is_remote
    results_wanted = 15 if results_wanted is None else results_wanted
    offset = 0 if offset is None else offset
    country_indeed = "usa" if country_indeed is None else country_indeed

    country_enum = Country.from_string(country_indeed)

    scraper_input = ScraperInput(
        site_type=site_type,
        country=country_enum,
        search_term=search_term,
        google_search_term=google_search_term,
        location=location,
        distance=distance,
        is_remote=is_remote,
        job_type=job_type,
        easy_apply=easy_apply,
        description_format=description_format,
        fetch_description=fetch_description or False,
        linkedin_fetch_description=linkedin_fetch_description or False,
        results_wanted=results_wanted,
        linkedin_company_ids=linkedin_company_ids,
        offset=offset,
        hours_old=hours_old,
    )

    def scrape_site(site: Site) -> tuple[str, JobResponse]:
        scraper_class = SCRAPER_MAPPING[site]
        scraper = scraper_class(proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)
        scraped_data: JobResponse = scraper.scrape(scraper_input)
        create_logger(scraper_class.__name__.removesuffix("Scraper")).info(
            "finished scraping"
        )
        return site.value, scraped_data

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(scrape_site, site) for site in site_type]
        site_to_jobs_dict = dict(future.result() for future in as_completed(futures))

    rows = []
    for site, job_response in site_to_jobs_dict.items():
        for job in job_response.jobs:
            job_data = job.model_dump()
            job_data["site"] = site
            job_data["company"] = job_data["company_name"]
            job_data["job_type"] = (
                ", ".join(job_type.value[0] for job_type in job_data["job_type"])
                if job_data["job_type"]
                else None
            )
            for name in ("emails", "skills"):
                job_data[name] = ", ".join(job_data[name]) if job_data[name] else None
            if job_data["location"]:
                job_data["location"] = Location(
                    **job_data["location"]
                ).display_location()

            job_data |= dict.fromkeys(
                ("interval", "min_amount", "max_amount", "currency", "salary_source")
            )
            if compensation := job_data["compensation"]:
                interval = compensation.pop("interval")
                job_data |= compensation
                job_data["interval"] = interval.value if interval else None
                job_data["salary_source"] = SalarySource.DIRECT_DATA.value
                if enforce_annual_salary and job_data["interval"] not in (
                    None,
                    "yearly",
                ):
                    convert_to_annual(job_data)
            elif country_enum == Country.USA:
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
            if not (job_data["min_amount"] or job_data["max_amount"]):
                job_data["salary_source"] = None
            rows.append(job_data)

    if not rows:
        return pd.DataFrame()
    jobs_df = pd.DataFrame(rows, columns=desired_order)
    return jobs_df.sort_values(
        by=["site", "date_posted"], ascending=[True, False]
    ).reset_index(drop=True)
