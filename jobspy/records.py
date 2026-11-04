from __future__ import annotations

import json
import os

import pandas as pd

from jobspy.model import JobPost

FIELDS = list(JobPost.model_fields)
PREVIEW = (
    "site title company location date_posted job_type is_remote min_amount max_amount"
    " currency interval job_url"
).split()
DEFAULT_SITES = ["indeed", "linkedin", "zip_recruiter", "glassdoor"]
REGIONAL = "bayt (Middle East), naukri (India), bdjobs (Bangladesh), hellowork (France), techjobs (Vietnam)"
FORMATS = (".csv", ".json", ".jsonl")


def records(jobs: pd.DataFrame, names: list[str]) -> list[dict[str, object]]:
    return [
        {name: rec[name] for name in names if not pd.isna(rec[name])}
        for rec in jobs[names].to_dict("records")
    ]


def dumps(value: object) -> str:
    return json.dumps(value, default=str, ensure_ascii=False, separators=(",", ":"))


def lines(jobs: pd.DataFrame, names: list[str]) -> list[str]:
    return [dumps(rec) + "\n" for rec in records(jobs, names)]


def save_path(path: str) -> str:
    if not path.lower().endswith(FORMATS):
        raise ValueError(f"{path}: use .csv, .json or .jsonl")
    return path


def save(jobs: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if path.lower().endswith(".csv"):
        jobs.to_csv(path, index=False)
    else:
        with open(path, "w", encoding="utf-8") as saved:
            if path.lower().endswith(".json"):
                saved.write(dumps(records(jobs, FIELDS)))
            else:
                saved.writelines(lines(jobs, FIELDS))


def commas(text: str) -> list[str]:
    return [name for part in text.split(",") if (name := part.strip())]
