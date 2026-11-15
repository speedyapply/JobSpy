"""Every job the runner has seen, in SQLite ($DATA_DIR/jobs.db), with what you did with
it: saved, applied or discarded, and a note. The API reads it, so looking at jobs again
never asks the job boards."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

FIELDS = [
    "job_url",
    "site",
    "search",
    "title",
    "company",
    "location",
    "date_posted",
    "is_remote",
    "work_from_home_type",
    "job_type",
    "min_amount",
    "max_amount",
    "interval",
    "currency",
    "description",
    "match",
    "match_notes",
    "match_detail",
    "first_seen",
]
COLUMNS = ", ".join(
    f"{name} TEXT UNIQUE NOT NULL" if name == "job_url" else name for name in FIELDS
)
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    {COLUMNS},
    saved_at TEXT,
    applied_at TEXT,
    hidden_at TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS jobs_first_seen ON jobs (first_seen);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""

# each list: which jobs, in what order
LISTS = {
    "recent": ("hidden_at IS NULL", "first_seen DESC, match DESC"),
    "top": (
        "hidden_at IS NULL AND applied_at IS NULL AND first_seen >= :since",
        "match DESC, first_seen DESC",
    ),
    "saved": ("saved_at IS NOT NULL", "saved_at DESC"),
    "applied": ("applied_at IS NOT NULL", "applied_at DESC"),
    "hidden": ("hidden_at IS NOT NULL", "hidden_at DESC"),
    "all": ("1", "first_seen DESC"),
}
FLAGS = {"saved": "saved_at", "applied": "applied_at", "hidden": "hidden_at"}
SEARCHED = (
    "lower(coalesce(title,'') || ' ' || coalesce(company,'') || ' ' || "
    "coalesce(location,'') || ' ' || coalesce(description,'')) LIKE ?"
)


def clean(value: object) -> object:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if hasattr(value, "item"):  # numpy scalars
        return value.item()
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    return None if text in ("", "nan", "None", "NaT") else text


def number(value: object) -> float | None:
    try:
        return None if value is None else float(str(value))
    except ValueError:
        return None


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def to_json(row: sqlite3.Row, description: bool = True) -> dict[str, object]:
    """A stored job as the API sends it"""
    job = dict(row)
    try:
        detail = json.loads(job.pop("match_detail") or "{}")
    except ValueError:
        detail = {}
    low, high = number(job.pop("min_amount")), number(job.pop("max_amount"))
    interval, currency = job.pop("interval"), job.pop("currency")
    job["salary"] = (
        {"min": low, "max": high, "interval": interval, "currency": currency}
        if low is not None or high is not None
        else None
    )
    job["is_remote"] = str(job.get("is_remote")).lower() in ("1", "true")
    job["match"] = None if job.get("match") is None else int(float(job["match"]))
    job["match_detail"] = {
        "have": detail.get("have", []),
        "missing": detail.get("missing", []),
        "warnings": detail.get("warnings", []),
        "title_only": bool(detail.get("title_only", False)),
    }
    job.pop("match_notes", None)
    job["has_description"] = bool(job.get("description"))
    if not description:
        job.pop("description", None)
    return job


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def db(self) -> Iterator[sqlite3.Connection]:
        """A connection per use: the API and the search loop share the file."""
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    # writing

    def add(self, jobs: pd.DataFrame) -> dict[str, int]:
        """Adds the jobs not stored yet; returns the id of every job_url given."""
        rows = [
            {name: clean(job.get(name)) for name in FIELDS}
            for job in jobs.to_dict("records")
        ]
        for row in rows:  # numbers from a CSV come as text; keep them sortable
            for name in ("match", "min_amount", "max_amount"):
                row[name] = number(row[name])
            if row["match"] is not None:
                row["match"] = int(row["match"])
        with self.db() as db:
            db.executemany(
                f"INSERT OR IGNORE INTO jobs ({', '.join(FIELDS)}) "
                f"VALUES ({', '.join(':' + name for name in FIELDS)})",
                rows,
            )
            urls = [row["job_url"] for row in rows]
            found = {}
            for start in range(0, len(urls), 500):
                chunk = urls[start : start + 500]
                marks = ", ".join("?" * len(chunk))
                for row in db.execute(
                    f"SELECT id, job_url FROM jobs WHERE job_url IN ({marks})", chunk
                ):
                    found[row["job_url"]] = row["id"]
        return found

    def import_csv(self, path: Path) -> int:
        """Loads an older jobs.csv once, when the database is still empty."""
        if not path.exists() or self.count() > 0:
            return 0
        jobs = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if "job_url" not in jobs:
            return 0
        return len(self.add(jobs[jobs["job_url"] != ""]))

    def update(self, job_id: int, changes: dict[str, object]) -> bool:
        """saved / applied / hidden: true or false; note: text or null.
        Returns False when there is no such job."""
        sets: dict[str, object] = {}
        stamp = now()
        for flag, column in FLAGS.items():
            if flag in changes:
                sets[column] = stamp if changes[flag] else None
        if "note" in changes:
            note = changes["note"]
            sets["note"] = str(note).strip() or None if note is not None else None
        with self.db() as db:
            row = db.execute(
                "SELECT saved_at, applied_at, hidden_at FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return False
            for column in FLAGS.values():  # keep the first time a flag was set
                if sets.get(column) and row[column]:
                    sets[column] = row[column]
            if sets.get("applied_at") and "saved_at" not in sets:
                # applied jobs stay in the saved list too
                sets["saved_at"] = row["saved_at"] or stamp
            if sets:
                assignments = ", ".join(f"{column} = :{column}" for column in sets)
                db.execute(
                    f"UPDATE jobs SET {assignments} WHERE id = :id",
                    sets | {"id": job_id},
                )
        return True

    # reading

    def seen(self) -> tuple[set[str], list[tuple[str, str]]]:
        """The job_urls stored, and their titles and companies, to skip repeats."""
        with self.db() as db:
            rows = db.execute("SELECT job_url, title, company FROM jobs").fetchall()
        return {r["job_url"] for r in rows}, [(r["title"], r["company"]) for r in rows]

    def get(self, job_id: int) -> sqlite3.Row | None:
        with self.db() as db:
            return db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()

    def page(
        self,
        name: str,
        query: str = "",
        offset: int = 0,
        limit: int = 20,
        days: int = 7,
        min_match: int = 0,
        remote: bool = False,
    ) -> tuple[list[sqlite3.Row], int]:
        """One page of a list, optionally only jobs that have every word of query,
        reach min_match, or are remote"""
        where, order = LISTS[name]
        words = [w for w in query.lower().split() if w][:6]
        if words:
            where = f"({where}) AND " + " AND ".join(SEARCHED for _ in words)
        if min_match:
            where = f"({where}) AND match >= :min_match"
        if remote:
            where = (
                f"({where}) AND (lower(is_remote) IN ('1', 'true') OR "
                "lower(coalesce(work_from_home_type, '')) LIKE '%teletrabajo%' OR "
                "lower(coalesce(work_from_home_type, '')) LIKE '%remot%')"
            )
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
        named: dict[str, object] = {"since": since, "min_match": min_match}
        # mix named and positional parameters: name the search words too
        for i, _ in enumerate(words):
            where = where.replace("LIKE ?", f"LIKE :w{i}", 1)
            named[f"w{i}"] = f"%{words[i]}%"
        with self.db() as db:
            total = db.execute(
                f"SELECT COUNT(*) FROM jobs WHERE {where}", named
            ).fetchone()[0]
            rows = db.execute(
                f"SELECT * FROM jobs WHERE {where} ORDER BY {order} "
                "LIMIT :limit OFFSET :offset",
                named | {"limit": limit, "offset": offset},
            ).fetchall()
        return rows, int(total)

    def updates(
        self, after: int, min_match: int = 0, limit: int = 50
    ) -> tuple[list[sqlite3.Row], int, int]:
        """Jobs stored after id `after` (not discarded, at least min_match), best
        first; how many there are; and the newest id, to ask from next time"""
        where = "id > :after AND hidden_at IS NULL AND coalesce(match, 0) >= :min_match"
        args = {"after": after, "min_match": min_match, "limit": limit}
        with self.db() as db:
            total = db.execute(
                f"SELECT COUNT(*) FROM jobs WHERE {where}", args
            ).fetchone()[0]
            rows = db.execute(
                f"SELECT * FROM jobs WHERE {where} "
                "ORDER BY match DESC, id DESC LIMIT :limit",
                args,
            ).fetchall()
            newest = db.execute("SELECT coalesce(MAX(id), 0) FROM jobs").fetchone()[0]
        return rows, int(total), int(newest)

    def rescore(
        self, score: Callable[[dict[str, object]], tuple[int, str, str]]
    ) -> int:
        """Scores every stored job again (after the profile changed);
        score(job) -> (match, match_notes, match_detail)"""
        with self.db() as db:
            rows = db.execute(
                "SELECT id, title, description, location, is_remote, "
                "work_from_home_type FROM jobs"
            ).fetchall()
            updates = [(*score(dict(row)), row["id"]) for row in rows]
            db.executemany(
                "UPDATE jobs SET match = ?, match_notes = ?, match_detail = ? "
                "WHERE id = ?",
                updates,
            )
        return len(updates)

    def count(self) -> int:
        with self.db() as db:
            return int(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])

    def stats(self) -> dict[str, object]:
        week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
        with self.db() as db:
            one = db.execute(
                "SELECT COUNT(*) total, COUNT(saved_at) saved, "
                "COUNT(applied_at) applied, COUNT(hidden_at) hidden, "
                "coalesce(SUM(first_seen >= ?), 0) week, "
                "coalesce(SUM(match >= 70 AND first_seen >= ?), 0) good_week "
                "FROM jobs",
                (week, week),
            ).fetchone()
            sites = db.execute(
                "SELECT coalesce(site, '?') site, COUNT(*) n FROM jobs "
                "GROUP BY site ORDER BY n DESC"
            ).fetchall()
        return dict(one) | {"sites": {r["site"]: r["n"] for r in sites}}

    def export(self, names: list[str]) -> pd.DataFrame:
        wheres = " OR ".join(f"({LISTS[name][0]})" for name in names)
        with self.db() as db:
            jobs = pd.read_sql_query(
                f"SELECT * FROM jobs WHERE {wheres} ORDER BY first_seen DESC",
                db,
                params={"since": ""},
            )
        return jobs.drop(columns=["match_detail"], errors="ignore")

    # settings

    def setting(self, key: str, default: str | None = None) -> str | None:
        with self.db() as db:
            row = db.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row[0] if row else default

    def set(self, key: str, value: str | None) -> None:
        with self.db() as db:
            db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
