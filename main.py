
import click
from pandas import DataFrame
from config import RUN_ID, RUN_DIR
import csv
from jobspy import scrape_jobs
from os import path

SITES = [
    "indeed",
    "linkedin",
    # "zip_recruiter",
    # "glassdoor",
    # "google",
    # "bayt",
    # "naukri",
]
TITLE_FILTERS = [
    "Full Stack",
    "Front End",
    "Frontend",
    "Front-End",
    ".Net",
    'Intern',
    'New Grad',
    'Junior',
    "Jr",
    "Unity",
    "C#",
    "BIOS",
    "Firmware",
    "React"
]


def filter_results(df):
    ...


def run(

):
    print(f"Starting Run: {RUN_ID}")
    jobs = scrape_jobs(
        site_name=SITES,
        search_term="software engineer",
        is_remote=True,
        results_wanted=10,
        hours_old=24,
        country_indeed="USA",
        linkedin_fetch_description=True,
    )
    print(f"Found {len(jobs)} jobs - raw")
    raw_jobs = jobs.copy()
    export("raw", raw_jobs)
    jobs = filter_by_title(jobs)
    jobs = filter_is_remote(jobs)
    jobs = cleanup_columns(jobs)
    export("run", jobs)


def cleanup_columns(df) -> DataFrame:
    cols = [

        'company',
        'title',
        'date_posted',

        'id',
        'site',
        'job_url',
        'job_url_direct',

        'location',

        'job_type',
        'salary_source',
        'interval',
        'min_amount',
        'max_amount',
        'currency',
        'is_remote',
        'job_level',
        'job_function',
        # 'listing_type',
        # 'emails',
        'description',
        'company_industry',
        'company_url',
        # 'company_logo',
        # 'company_url_direct',
        # 'company_addresses',
        # 'company_num_employees',
        # 'company_revenue',
        # 'company_description',
        # 'skills',
        # 'experience_range',
        # 'company_rating',
        # 'company_reviews_count',
        # 'vacancy_count',
        # 'work_from_home_type'
    ]
    return df.loc[:, cols]


def filter_by_title(df: DataFrame) -> DataFrame:
    return df[~df["title"].apply(lambda x: any(f in x for f in TITLE_FILTERS))]


def filter_is_remote(df: DataFrame):
    return df[~df.is_remote != True]


def export(name, df):
    # to_excel

    out_file = path.join(RUN_DIR, f"{name}.csv")
    df.to_csv(
        out_file,
        quoting=csv.QUOTE_NONNUMERIC,
        escapechar="\\",
        index=False
    )


@click.group()
def cli():
    pass


if __name__ == "__main__":
    run()
