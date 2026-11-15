"""The searches: run those in searches.json every few hours, score each new job
against profile.json and store it in $DATA_DIR/jobs.db (and jobs.csv, for Excel).

`python api.py` runs this loop in the background behind the API the app talks to;
`python run.py` runs it alone, and with INTERVAL_HOURS=0 runs the searches once.

Environment:
  SEARCHES        path of the searches file (default /app/searches.json)
  DATA_DIR        where jobs.db and the CSVs go (default /data)
  INTERVAL_HOURS  hours between runs (default 6); 0 runs once and exits
  PROFILE         the starting profile for the compatibility score (default
                  /app/profile.json); the app edits a copy in $DATA_DIR/profile.json
  SEARCH_PAUSE    seconds between two searches, e.g. 10 or 5-15 (default 5-15)
  INFOJOBS_DELAY  seconds between two InfoJobs requests, e.g. 4 or 3-6 (default 3-6)
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import shutil
import threading
import time
import unicodedata
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

import match
import pandas as pd
from store import Store

from jobspy import scrape_jobs

log = logging.getLogger("runner")
SEARCHES = Path(os.environ.get("SEARCHES", "/app/searches.json"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
PROFILE = Path(os.environ.get("PROFILE", "/app/profile.json"))
INTERVAL_HOURS = float(os.environ.get("INTERVAL_HOURS", "6"))
_pause = os.environ.get("SEARCH_PAUSE", "5-15").partition("-")
SEARCH_PAUSE = (float(_pause[0]), float(_pause[2] or _pause[0]))
LAST_ERRORS: list[str] = []
COLUMNS = [
    "first_seen",
    "match",
    "match_notes",
    "search",
    "site",
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
    "job_url",
    "description",
]


def normalise(text: object) -> str:
    """Lower case, no accents or punctuation: the same job on two boards matches."""
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", " ", text.decode().lower()).strip()


def dedup_key(jobs: pd.DataFrame) -> pd.Series:
    return jobs["title"].map(normalise) + "|" + jobs["company"].map(normalise)


def load_searches() -> list[dict[str, object]]:
    searches = json.loads(SEARCHES.read_text(encoding="utf-8"))
    if not isinstance(searches, list) or not searches:
        raise ValueError(f"{SEARCHES}: expected a non-empty list of searches")
    return searches


def run_once(store: Store) -> int:
    """Runs every search once; returns how many new jobs it stored"""
    LAST_ERRORS.clear()
    all_csv = DATA_DIR / "jobs.csv"
    seen = (
        pd.read_csv(all_csv, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if all_csv.exists()
        else pd.DataFrame(columns=COLUMNS)
    )
    stored_urls, stored_names = store.seen()
    stored = pd.DataFrame(stored_names, columns=["title", "company"])
    seen_urls = set(seen["job_url"]) | stored_urls
    seen_keys = (set(dedup_key(seen)) if len(seen) else set()) | (
        set(dedup_key(stored)) if len(stored) else set()
    )
    found = []

    for search in load_searches():
        params = dict(search)
        name = str(params.pop("name", params.get("search_term", "search")))
        params.setdefault("verbose", 1)
        log.info(f"searching {name!r} on {params.get('site_name')}")
        try:
            jobs = scrape_jobs(**params)
        except Exception as e:
            log.error(f"{name}: {e}")
            LAST_ERRORS.append(f"{name}: {e}")
            continue
        for site, error in jobs.attrs.get("errors", {}).items():
            log.error(f"{name} / {site}: {error}")
            LAST_ERRORS.append(f"{name} / {site}: {error}")
        log.info(f"{name}: {len(jobs)} jobs")
        if len(jobs):
            found.append(jobs.assign(search=name))
        time.sleep(random.uniform(*SEARCH_PAUSE))

    if not found:
        log.info("no jobs found this run")
        return 0
    jobs = pd.concat(found, ignore_index=True)
    jobs["key"] = dedup_key(jobs)
    jobs = jobs[~jobs["job_url"].isin(seen_urls) & ~jobs["key"].isin(seen_keys)]
    jobs = jobs.drop_duplicates("job_url").drop_duplicates("key")
    if jobs.empty:
        log.info("nothing new this run")
        return 0

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    jobs = jobs.assign(first_seen=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if (path := profile_path()).exists():
        profile = match.Profile(path)
        scores = [scored(profile, job) for job in jobs.to_dict("records")]
        jobs["match"] = [m[0] for m in scores]
        jobs["match_notes"] = [m[1] for m in scores]
        jobs["match_detail"] = [m[2] for m in scores]
        jobs = jobs.sort_values("match", ascending=False)
    else:
        log.warning(f"{path} not found: no compatibility score")
    new = jobs.reindex(columns=COLUMNS)
    (DATA_DIR / "new").mkdir(parents=True, exist_ok=True)
    stamp = now.replace(" ", "_").replace(":", "")
    new.to_csv(DATA_DIR / "new" / f"{stamp}.csv", index=False, encoding="utf-8-sig")
    # the whole file is rewritten, so new columns line up with the old rows
    pd.concat(
        [seen.reindex(columns=COLUMNS), new.astype(str).replace("nan", "")]
    ).to_csv(all_csv, index=False, encoding="utf-8-sig")
    log.info(f"{len(new)} new jobs -> {DATA_DIR / 'new' / f'{stamp}.csv'}")
    store.add(jobs)
    return len(new)


def run_and_record(store: Store) -> None:
    """One run, with its time, outcome and errors kept for the API to show"""
    store.set("running", "1")
    started = datetime.now()
    try:
        found = run_once(store)
        outcome = {"new": found, "errors": LAST_ERRORS[:]}
    except Exception as e:
        log.exception("run failed")
        outcome = {"new": 0, "errors": [str(e)]}
    finally:
        store.set("running", None)
    store.set("last_run", started.isoformat(timespec="seconds"))
    store.set("last_run_result", json.dumps(outcome, ensure_ascii=False))


def loop(store: Store, stop: threading.Event | None = None) -> None:
    """Runs the searches now and then every INTERVAL_HOURS, until stop is set"""
    stop = stop or threading.Event()
    while not stop.is_set():
        run_and_record(store)
        if INTERVAL_HOURS <= 0:
            return
        # a little jitter so the runs don't hit the boards at the same minute
        pause = INTERVAL_HOURS * 3600 * random.uniform(0.9, 1.1)
        next_run = datetime.now() + timedelta(seconds=pause)
        store.set("next_run", next_run.isoformat(timespec="seconds"))
        log.info(f"next run in {pause / 3600:.1f} h")
        stop.wait(pause)


def scored(profile: match.Profile, job: dict[str, object]) -> tuple[int, str, str]:
    """A job's match, its notes, and its detail as stored"""
    m = profile.score(job)
    detail = {k: v for k, v in asdict(m).items() if k != "score"}
    return m.score, m.notes(), json.dumps(detail, ensure_ascii=False)


def rescore_all(store: Store) -> int:
    """Scores every stored job against the current profile again"""
    path = profile_path()
    if not path.exists():
        return 0
    profile = match.Profile(path)
    return store.rescore(lambda job: scored(profile, job))


def profile_path() -> Path:
    """The profile in use: $DATA_DIR/profile.json, which the app edits, started from
    PROFILE the first time"""
    path = DATA_DIR / "profile.json"
    if not path.exists() and PROFILE.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROFILE, path)
    return path


def open_store() -> Store:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    store = Store(DATA_DIR / "jobs.db")
    store.set("running", None)  # a run cut short by a restart isn't running
    if imported := store.import_csv(DATA_DIR / "jobs.csv"):
        log.info(f"imported {imported} jobs from jobs.csv into jobs.db")
    return store


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    loop(open_store())


if __name__ == "__main__":
    main()
