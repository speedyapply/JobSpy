from __future__ import annotations

import csv
import json
import os
import re
import smtplib
import sys
import unicodedata
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jobspy import scrape_jobs

load_dotenv(SCRIPT_DIR / ".env")
load_dotenv(SCRIPT_DIR / ".env.local", override=True)

MASTER_CSV_PATH = Path("jobs_master.csv")
REPORT_MD_PATH = Path("reports/latest.md")

SEARCH_TERM = os.getenv("JOB_SEARCH_TERM", "Software Engineer")
LOCATION = os.getenv("JOB_LOCATION", "United States")
RESULTS_WANTED = int(os.getenv("JOB_RESULTS_WANTED", "700"))
HOURS_OLD = int(os.getenv("JOB_HOURS_OLD", "1"))
APPLICANT_LIMIT = int(os.getenv("JOB_APPLICANT_LIMIT", "200"))
MAX_YOE_REQUIRED = int(os.getenv("JOB_MAX_YOE_REQUIRED", "0"))
YOE_CHECKPOINT_PATH = os.getenv("YOE_CHECKPOINT_PATH", "yoe_checkpoint.csv")
EXCLUDED_COMPANIES_RAW = os.getenv("JOB_EXCLUDED_COMPANIES", "")
EXCLUDED_COMPANIES_FILE = (
    os.getenv("JOB_EXCLUDED_COMPANIES_FILE") or "excluded_companies.txt"
)
EXCLUDED_COMPANY_KEYWORDS_RAW = os.getenv("JOB_EXCLUDED_COMPANY_KEYWORDS", "")
EXCLUDED_COMPANY_KEYWORDS_FILE = os.getenv("JOB_EXCLUDED_COMPANY_KEYWORDS_FILE") or ""

FINAL_COLUMNS = [
    "id",
    "site",
    "job_url",
    "job_url_direct",
    "title",
    "company",
    "location",
    "date_posted",
    "applicants",
    "yoe_required",
    "extracted_time",
]

_MOJI_REPLACEMENTS = {
    "Ãƒâ€”": "Ã—",
    "Ã¢â‚¬â€": "â€”",
    "Ã¢â‚¬â€œ": "â€“",
    "Ã¢â‚¬Ëœ": "â€˜",
    "Ã¢â‚¬â„¢": "â€™",
    "Ã¢â‚¬Å“": "â€œ",
    "Ã¢â‚¬ï¿½": "â€",
    "Ã‚": "",
}


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    for bad, good in _MOJI_REPLACEMENTS.items():
        text = text.replace(bad, good)
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_key(value: object) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_env_list(value: str) -> list[str]:
    value = (value or "").strip()
    if not value:
        return []

    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass

    return [item.strip() for item in re.split(r"[,;\n]+", value or "") if item.strip()]


def load_list_from_file(file_value: str) -> set[str]:
    if not file_value:
        return set()

    file_path = Path(file_value)
    if not file_path.is_absolute():
        file_path = SCRIPT_DIR / file_path

    values = set()
    if file_path.exists():
        for line in file_path.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                values.add(value)

    return values


def load_excluded_companies() -> set[str]:
    companies = set(split_env_list(EXCLUDED_COMPANIES_RAW))
    companies.update(load_list_from_file(EXCLUDED_COMPANIES_FILE))
    return {norm_key(company) for company in companies}


def load_excluded_company_keywords() -> list[str]:
    keywords = set(split_env_list(EXCLUDED_COMPANY_KEYWORDS_RAW))
    keywords.update(load_list_from_file(EXCLUDED_COMPANY_KEYWORDS_FILE))
    return sorted(norm_key(keyword) for keyword in keywords if norm_key(keyword))


def keep_final_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in FINAL_COLUMNS:
        if column not in out.columns:
            out[column] = ""
    return out[FINAL_COLUMNS].copy()


def find_description_column(df: pd.DataFrame) -> str:
    for column in ["description", "job_description", "job_desc"]:
        if column in df.columns:
            return column
    return "description"


def load_master() -> pd.DataFrame | None:
    if not MASTER_CSV_PATH.exists():
        return None
    try:
        return pd.read_csv(MASTER_CSV_PATH)
    except Exception:
        return None


def prepare_jobs_for_dedupe(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    for column in ["title", "company", "location"]:
        if column not in work.columns:
            work[column] = ""
        work[column] = work[column].astype(str).fillna("").map(clean_text)

    work["title_norm"] = work["title"].map(norm_key)
    work["company_norm"] = work["company"].map(norm_key)
    work["location_norm"] = work["location"].map(norm_key)
    return work


def internal_dedupe_new_batch(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if "site" in work.columns and "id" in work.columns:
        work = work.drop_duplicates(subset=["site", "id"], keep="first")
    return work.drop_duplicates(
        subset=["title_norm", "company_norm", "location_norm"],
        keep="first",
    )


def filter_new_vs_master(
    master: pd.DataFrame | None, new_jobs: pd.DataFrame
) -> pd.DataFrame:
    if master is None or master.empty:
        return new_jobs

    master_work = prepare_jobs_for_dedupe(master)

    site_id_keys = set()
    if "site" in master_work.columns and "id" in master_work.columns:
        site_id_keys = set(
            zip(master_work["site"].astype(str), master_work["id"].astype(str))
        )

    title_company_location_keys = set(
        zip(
            master_work["title_norm"],
            master_work["company_norm"],
            master_work["location_norm"],
        )
    )

    keep_rows = []
    for _, row in new_jobs.iterrows():
        site_id_key = (str(row.get("site", "")), str(row.get("id", "")))
        title_company_location_key = (
            row.get("title_norm", ""),
            row.get("company_norm", ""),
            row.get("location_norm", ""),
        )

        if site_id_key in site_id_keys:
            continue
        if title_company_location_key in title_company_location_keys:
            continue
        keep_rows.append(row)

    return pd.DataFrame(keep_rows) if keep_rows else new_jobs.iloc[0:0].copy()


def filter_excluded_companies(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    excluded_exact = load_excluded_companies()
    excluded_keywords = load_excluded_company_keywords()

    if not excluded_exact and not excluded_keywords:
        print("Company filter: no excluded companies configured")
        return df

    print(
        "Company filter: loaded "
        f"{len(excluded_exact)} exact exclusions and "
        f"{len(excluded_keywords)} keyword exclusions"
    )

    work = df.copy()
    if "company" not in work.columns:
        work["company"] = ""

    company_norm = work["company"].map(norm_key)
    excluded_mask = company_norm.map(
        lambda company: company in excluded_exact
        or any(keyword in company for keyword in excluded_keywords)
    )
    filtered = work.loc[~excluded_mask].copy()

    print(
        f"Company filter: removed {int(excluded_mask.sum())} of {len(work)} jobs "
        "from excluded companies"
    )
    return filtered


def parse_applicant_count(applicants: object) -> int | None:
    text = clean_text(applicants).lower()
    if not text:
        return None

    if "over 200" in text or "more than 200" in text:
        return APPLICANT_LIMIT + 1

    first_match = re.search(r"first\s+(\d+)", text)
    if first_match:
        return int(first_match.group(1))

    applicants_match = re.search(r"(\d[\d,]*)\s+applicants?", text)
    if applicants_match:
        return int(applicants_match.group(1).replace(",", ""))

    return None


def filter_under_applicant_limit(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    work = df.copy()
    if "applicants" not in work.columns:
        work["applicants"] = ""

    applicant_counts = work["applicants"].map(parse_applicant_count)
    filtered = work.loc[
        applicant_counts.notna() & (applicant_counts < APPLICANT_LIMIT)
    ].copy()

    print(
        f"Applicant filter: kept {len(filtered)} of {len(work)} jobs "
        f"with fewer than {APPLICANT_LIMIT} applicants"
    )
    return filtered


def filter_by_max_yoe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    work = df.copy()
    if "yoe_required" not in work.columns:
        work["yoe_required"] = 0

    yoe = pd.to_numeric(work["yoe_required"], errors="coerce").fillna(0)
    filtered = work.loc[yoe <= MAX_YOE_REQUIRED].copy()
    print(
        f"YOE filter: kept {len(filtered)} of {len(work)} jobs "
        f"with YOE <= {MAX_YOE_REQUIRED}"
    )
    return filtered


def build_markdown_report(df: pd.DataFrame) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        (
            f"# LinkedIn jobs under {APPLICANT_LIMIT} applicants and "
            f"YOE <= {MAX_YOE_REQUIRED} ({now})"
        ),
        "",
    ]

    if df is None or df.empty:
        lines.append("_No new jobs matched this run._")
        return "\n".join(lines)

    df = sort_for_notification(df)

    lines.append("| Title | Company | Job Link | Applicants | YOE Required |")
    lines.append("|---|---|---|---|---:|")

    for _, row in df.iterrows():
        title = str(row.get("title", "")).replace("|", "\\|")
        company = str(row.get("company", "")).replace("|", "\\|")
        applicants = str(row.get("applicants", "") or "").replace("|", "\\|")
        yoe_required = str(row.get("yoe_required", "") or "")
        job_url = str(row.get("job_url", "") or "").strip()
        link = f"[link]({job_url})" if job_url else ""
        lines.append(f"| {title} | {company} | {link} | {applicants} | {yoe_required} |")

    return "\n".join(lines)


def write_markdown_report(df: pd.DataFrame) -> None:
    REPORT_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD_PATH.write_text(build_markdown_report(df).strip() + "\n", encoding="utf-8")


def df_to_plain_table(df: pd.DataFrame) -> str:
    columns = ["title", "company", "job_url", "applicants", "yoe_required"]
    table = sort_for_notification(df)
    for column in columns:
        if column not in table.columns:
            table[column] = ""
    table = table[columns]
    table.columns = ["Title", "Company", "Job Link", "Applicants", "YOE Required"]
    return table.to_string(index=False)


def df_to_html_table(df: pd.DataFrame) -> str:
    rows = []
    df = sort_for_notification(df)
    for _, row in df.iterrows():
        job_url = str(row.get("job_url", "") or "").strip()
        link_html = f'<a href="{job_url}">link</a>' if job_url else ""
        rows.append(
            "<tr>"
            f"<td>{row.get('title', '')}</td>"
            f"<td>{row.get('company', '')}</td>"
            f"<td>{link_html}</td>"
            f"<td>{row.get('applicants', '')}</td>"
            f"<td>{row.get('yoe_required', '')}</td>"
            "</tr>"
        )

    return (
        "<table border='1' cellpadding='6' cellspacing='0'>"
        "<thead><tr>"
        "<th>Title</th><th>Company</th><th>Job Link</th>"
        "<th>Applicants</th><th>YOE Required</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def sort_for_notification(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    sorted_df = df.copy()
    sorted_df["__yoe_sort"] = pd.to_numeric(
        sorted_df.get("yoe_required", 0), errors="coerce"
    ).fillna(0)
    return sorted_df.sort_values(
        by=["__yoe_sort", "company", "title"], ascending=True
    ).drop(columns=["__yoe_sort"])


def send_email(subject: str, body_text: str, body_html: str | None = None) -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASS", "").strip()
    to_addr = os.getenv("EMAIL_TO", "").strip()
    from_addr = os.getenv("EMAIL_FROM", "").strip() or user

    if not (host and user and password and to_addr):
        print("Email not sent: missing SMTP_HOST/SMTP_USER/SMTP_PASS/EMAIL_TO.")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    return True


def save_master(master: pd.DataFrame | None, new_rows: pd.DataFrame) -> None:
    if master is None or master.empty:
        final = keep_final_columns(new_rows)
    else:
        final = pd.concat([keep_final_columns(master), keep_final_columns(new_rows)])
        final = final.drop_duplicates(subset=["site", "id"], keep="first")

    final.to_csv(
        MASTER_CSV_PATH,
        index=False,
        quoting=csv.QUOTE_MINIMAL,
        escapechar="\\",
    )
    print(f"Saved master: {len(final)} rows -> {MASTER_CSV_PATH}")


def main() -> None:
    from enrich_yoe import enrich_jobs_with_yoe

    master = load_master()

    new_jobs = scrape_jobs(
        site_name=["linkedin"],
        search_term=SEARCH_TERM,
        location=LOCATION,
        results_wanted=RESULTS_WANTED,
        hours_old=HOURS_OLD,
        linkedin_fetch_description=True,
    )

    if new_jobs is None or new_jobs.empty:
        print("No jobs scraped.")
        write_markdown_report(pd.DataFrame())
        return

    new_jobs = prepare_jobs_for_dedupe(new_jobs)
    new_jobs = internal_dedupe_new_batch(new_jobs)
    new_jobs = filter_new_vs_master(master, new_jobs)
    print(f"After dedupe vs master: {len(new_jobs)} new unique jobs")

    new_jobs = filter_excluded_companies(new_jobs)

    candidate_jobs = filter_under_applicant_limit(new_jobs)
    if candidate_jobs.empty:
        write_markdown_report(pd.DataFrame())
        print("No new jobs under applicant limit to evaluate.")
        return

    desc_col = find_description_column(candidate_jobs)
    candidate_jobs["_desc"] = candidate_jobs[desc_col].astype(str).fillna("").str.strip()
    candidate_jobs = candidate_jobs.loc[candidate_jobs["_desc"].str.len() > 0].copy()
    candidate_jobs.drop(columns=["_desc"], inplace=True)

    if candidate_jobs.empty:
        write_markdown_report(pd.DataFrame())
        print("No new jobs with descriptions to evaluate.")
        return

    enriched_jobs = enrich_jobs_with_yoe(
        candidate_jobs,
        desc_col,
        checkpoint_path=YOE_CHECKPOINT_PATH,
        checkpoint_every=10,
    )

    jobs_to_notify = filter_by_max_yoe(enriched_jobs)
    jobs_to_notify = keep_final_columns(jobs_to_notify)
    write_markdown_report(jobs_to_notify)

    if jobs_to_notify.empty:
        print("No new jobs under applicant and YOE limits to notify.")
        return

    email_sent = send_email(
        subject=(
            f"[LinkedIn jobs under {APPLICANT_LIMIT} applicants, "
            f"YOE <= {MAX_YOE_REQUIRED}] "
            f"{len(jobs_to_notify)} new jobs"
        ),
        body_text=(
            f"LinkedIn jobs under {APPLICANT_LIMIT} applicants "
            f"and YOE <= {MAX_YOE_REQUIRED}:\n\n"
            + df_to_plain_table(jobs_to_notify)
        ),
        body_html=(
            f"<h3>LinkedIn jobs under {APPLICANT_LIMIT} applicants "
            f"and YOE <= {MAX_YOE_REQUIRED}</h3>"
            + df_to_html_table(jobs_to_notify)
        ),
    )

    if email_sent:
        print(f"Emailed {len(jobs_to_notify)} jobs.")
        save_master(master, keep_final_columns(enriched_jobs))
        print(f"Wrote report: {REPORT_MD_PATH}")
    else:
        print("Master was not updated because email was not sent.")


if __name__ == "__main__":
    main()
