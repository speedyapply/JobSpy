"""SQLite persistence for the job monitor.

Two tables: `jobs` (one row per unique job_url, with first/last seen timestamps
and active/gone status) and `runs` (one row per scrape run for diagnostics).

Each `jobs` row also carries a `signature` — a normalized
(company, title, location-city) hash used to dedupe the same posting
when it shows up in multiple sources (e.g. the same Apple London role
appears in JobSpy/Indeed AND in SimplifyJobs/New-Grad-Positions). The
URL stays the PK; the signature only matters at render time.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator


# Tables only — indexes are created after migrations because some indexes
# reference columns added by ALTER TABLE (e.g. `region`). On a legacy DB
# the index would fail validation otherwise.
_SCHEMA_TABLES = """
CREATE TABLE IF NOT EXISTS jobs (
    job_url         TEXT PRIMARY KEY,
    site            TEXT,
    title           TEXT,
    company         TEXT,
    company_url     TEXT,
    location        TEXT,
    is_remote       INTEGER,
    date_posted     TEXT,
    description     TEXT,
    search_name     TEXT,
    min_amount      REAL,
    max_amount      REAL,
    currency        TEXT,
    salary_interval TEXT,
    region          TEXT,
    source_category TEXT,
    signature       TEXT,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS runs (
    run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    search_name  TEXT NOT NULL,
    rows_scraped INTEGER NOT NULL DEFAULT 0,
    rows_new     INTEGER NOT NULL DEFAULT 0
);
"""

_SCHEMA_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen);
CREATE INDEX IF NOT EXISTS idx_jobs_status     ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_region     ON jobs(region);
CREATE INDEX IF NOT EXISTS idx_jobs_signature  ON jobs(signature);
"""

# Columns added after the original schema. Each statement is idempotent —
# `ALTER TABLE ADD COLUMN` errors if the column exists, which we swallow.
# This lets a DB created by an older monitor upgrade in place.
_MIGRATIONS = [
    "ALTER TABLE jobs ADD COLUMN min_amount REAL",
    "ALTER TABLE jobs ADD COLUMN max_amount REAL",
    "ALTER TABLE jobs ADD COLUMN currency TEXT",
    "ALTER TABLE jobs ADD COLUMN salary_interval TEXT",
    "ALTER TABLE jobs ADD COLUMN company_url TEXT",
    "ALTER TABLE jobs ADD COLUMN is_remote INTEGER",
    "ALTER TABLE jobs ADD COLUMN region TEXT",
    "ALTER TABLE jobs ADD COLUMN source_category TEXT",
    "ALTER TABLE jobs ADD COLUMN signature TEXT",
]


def setup_db(path: str | Path) -> sqlite3.Connection:
    """Open the SQLite DB and ensure the schema exists. Caller closes.

    The literal string `:memory:` short-circuits the path/mkdir dance and
    opens a transient in-process DB — used by `run.py --dry-run` so a
    smoke test doesn't have to touch the on-disk `jobs.db`.
    """
    if str(path) == ":memory:":
        conn = sqlite3.connect(":memory:")
    else:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_TABLES)
    for stmt in _MIGRATIONS:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # column already exists — this is the only expected error
    conn.executescript(_SCHEMA_INDEXES)
    # Backfill: anything without a region tag predates the multi-region work
    # and was scraped by the JobSpy EMEA pipeline. Tag it accordingly.
    conn.execute("UPDATE jobs SET region = 'emea' WHERE region IS NULL")
    # Backfill signatures for rows that predate the dedup work. Cheap to
    # run on every startup — only operates on rows where signature IS NULL.
    _backfill_signatures(conn)
    conn.commit()
    return conn


# --------------------------------------------------------------------------- #
# Signature (cross-source dedup)
# --------------------------------------------------------------------------- #

# Words to strip from the title before hashing — these are the ones that
# differ between sources for the same posting. SimplifyJobs writes
# "Software Engineer New Grad" while Indeed writes "Software Engineer -
# 2026 Grad"; without this, the two would have different signatures.
_TITLE_NOISE_RE = re.compile(
    r"\b(?:new\s*grad(?:uate)?|graduate|early[\s-]+career|"
    r"intern(?:ship)?|co[\s-]?op|student|junior|jr|associate|entry[\s-]+level|"
    r"early\s+talent|emerging\s+talent|future\s+talent|fresh(?:er)?|"
    r"trainee|programme?|apprentice(?:ship)?|"
    r"f/m/x|f/m/d|m/f/d|m/w/d|m/f/x|all\s+genders?|"
    r"h/f|w/m|m/w)\b",
    re.IGNORECASE,
)
_TITLE_PARENS_RE = re.compile(r"\([^)]*\)")
_TITLE_YEAR_RE = re.compile(r"\b20\d\d\b")
_NON_LETTER_RE = re.compile(r"[^a-z]")


def _norm_company(s: str) -> str:
    """Letters-only lowercase, capped — same canonical form for "Apple" /
    "Apple Inc." / "Apple Inc". Aggressive but safe for hashing."""
    s = (s or "").lower()
    # Drop common corp-suffixes before letter-stripping so "Apple Inc"
    # doesn't get a different hash from "Apple".
    s = re.sub(
        r"[,\s]+(?:llc|inc(?:orporated)?|ltd|limited|gmbh|ag|"
        r"s\.?a\.?|sarl|sas|n\.?v\.?|b\.?v\.?|plc|corp(?:oration)?|"
        r"company|co|holdings?|group|se|oyj|ab|aps|pte|pty)\.?\s*$",
        "",
        s,
    )
    return _NON_LETTER_RE.sub("", s)[:30]


def _norm_title(s: str) -> str:
    s = (s or "").lower()
    s = _TITLE_PARENS_RE.sub(" ", s)
    s = _TITLE_YEAR_RE.sub(" ", s)
    s = _TITLE_NOISE_RE.sub(" ", s)
    return _NON_LETTER_RE.sub("", s)[:60]


def _norm_first_city(s: str) -> str:
    """Take the first city in a multi-location string and letter-strip.

    Locations look like "London, UK", "London, ENG, GB", or
    "London, UK · Cambridge, UK". We split on `·` first (our renderer's
    separator), then on `,`, and take the leftmost token.
    """
    s = (s or "").lower()
    first = re.split(r"[·]", s)[0]
    first = first.split(",")[0]
    return _NON_LETTER_RE.sub("", first)[:25]


def compute_signature(row: dict) -> str:
    """Stable hash for cross-source dedup.

    Same role posted to multiple sources should collapse to the same
    signature most of the time. Failure modes worth knowing:
      - Different cities (London vs Cambridge) → different signatures
        (correctly, these ARE different roles)
      - Title with junior keyword on one side only ("Junior Software
        Engineer" vs "Software Engineer") → SAME signature (we strip
        seniority words)
      - Brand-new company name format ("Apple Inc." vs "Apple LLC") →
        SAME signature (we strip corp suffixes)
    """
    return "|".join(
        (
            _norm_company(row.get("company", "")),
            _norm_title(row.get("title", "")),
            _norm_first_city(row.get("location", "")),
        )
    )


def _backfill_signatures(conn: sqlite3.Connection) -> int:
    """One-shot fill of signatures for rows that predate the dedup work."""
    rows = conn.execute(
        "SELECT job_url, company, title, location FROM jobs "
        "WHERE signature IS NULL OR signature = ''"
    ).fetchall()
    if not rows:
        return 0
    for r in rows:
        sig = compute_signature(dict(r))
        conn.execute(
            "UPDATE jobs SET signature = ? WHERE job_url = ?",
            (sig, r["job_url"]),
        )
    return len(rows)


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def upsert_jobs(
    conn: sqlite3.Connection,
    rows: Iterable[dict],
    run_started_at: str,
    search_name: str,
) -> tuple[int, int]:
    """Insert new jobs / refresh last_seen on existing ones.

    Returns (rows_scraped, rows_new). A row is "new" if its first_seen equals
    the supplied run timestamp — that's how compute_diff finds net-new jobs.
    """
    scraped = 0
    new = 0
    with transaction(conn):
        for row in rows:
            scraped += 1
            url = row.get("job_url")
            if not url:
                continue
            # Compute signature once per row — used both as cross-source
            # dedup key at render time and for INSERT/UPDATE here.
            sig = compute_signature(row)
            existing = conn.execute(
                "SELECT job_url FROM jobs WHERE job_url = ?", (url,)
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE jobs
                       SET last_seen       = ?,
                           status          = 'active',
                           title           = COALESCE(?, title),
                           company         = COALESCE(?, company),
                           company_url     = COALESCE(?, company_url),
                           location        = COALESCE(?, location),
                           is_remote       = COALESCE(?, is_remote),
                           date_posted     = COALESCE(?, date_posted),
                           description     = COALESCE(?, description),
                           search_name     = COALESCE(?, search_name),
                           min_amount      = COALESCE(?, min_amount),
                           max_amount      = COALESCE(?, max_amount),
                           currency        = COALESCE(?, currency),
                           salary_interval = COALESCE(?, salary_interval),
                           region          = COALESCE(?, region),
                           source_category = COALESCE(?, source_category),
                           signature       = ?
                     WHERE job_url = ?
                    """,
                    (
                        run_started_at,
                        row.get("title"),
                        row.get("company"),
                        row.get("company_url"),
                        row.get("location"),
                        _coerce_bool(row.get("is_remote")),
                        row.get("date_posted"),
                        row.get("description"),
                        search_name,
                        row.get("min_amount"),
                        row.get("max_amount"),
                        row.get("currency"),
                        row.get("interval") or row.get("salary_interval"),
                        row.get("region"),
                        row.get("source_category"),
                        sig,
                        url,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO jobs
                        (job_url, site, title, company, company_url, location,
                         is_remote, date_posted, description, search_name,
                         min_amount, max_amount, currency, salary_interval,
                         region, source_category, signature,
                         first_seen, last_seen, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    """,
                    (
                        url,
                        row.get("site"),
                        row.get("title"),
                        row.get("company"),
                        row.get("company_url"),
                        row.get("location"),
                        _coerce_bool(row.get("is_remote")),
                        row.get("date_posted"),
                        row.get("description"),
                        search_name,
                        row.get("min_amount"),
                        row.get("max_amount"),
                        row.get("currency"),
                        row.get("interval") or row.get("salary_interval"),
                        row.get("region"),
                        row.get("source_category"),
                        sig,
                        run_started_at,
                        run_started_at,
                    ),
                )
                new += 1
    return scraped, new


def _coerce_bool(v):
    """SQLite has no native bool; store as 0/1, leave None alone."""
    if v is None:
        return None
    return 1 if v else 0


def mark_gone(conn: sqlite3.Connection, run_started_at: str) -> int:
    """Flip rows we didn't see this run from active to gone. Returns count."""
    with transaction(conn):
        cur = conn.execute(
            """
            UPDATE jobs
               SET status = 'gone'
             WHERE status = 'active'
               AND last_seen < ?
            """,
            (run_started_at,),
        )
        return cur.rowcount


def record_run(
    conn: sqlite3.Connection,
    started_at: str,
    search_name: str,
    rows_scraped: int,
    rows_new: int,
) -> None:
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO runs (started_at, search_name, rows_scraped, rows_new)
            VALUES (?, ?, ?, ?)
            """,
            (started_at, search_name, rows_scraped, rows_new),
        )


def fetch_new_since(conn: sqlite3.Connection, run_started_at: str) -> list[dict]:
    """Return jobs whose first_seen == this run's timestamp (i.e. net-new)."""
    rows = conn.execute(
        """
        SELECT job_url, site, title, company, location, date_posted, search_name
          FROM jobs
         WHERE first_seen = ?
           AND status = 'active'
         ORDER BY company, title
        """,
        (run_started_at,),
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_active(conn: sqlite3.Connection) -> list[dict]:
    """Return all currently-active jobs, newest first. Used by the renderer."""
    rows = conn.execute(
        """
        SELECT job_url, site, title, company, company_url, location, is_remote,
               date_posted, search_name, min_amount, max_amount, currency,
               salary_interval, region, source_category, signature,
               first_seen, last_seen
          FROM jobs
         WHERE status = 'active'
         ORDER BY first_seen DESC, company, title
        """
    ).fetchall()
    return [dict(r) for r in rows]
