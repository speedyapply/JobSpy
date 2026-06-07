from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError

API_KEY = os.getenv("NOVITA_API_KEY", "").strip()
if not API_KEY:
    raise RuntimeError("NOVITA_API_KEY is not set in your environment or .env file.")

BASE_URL = "https://api.novita.ai/openai"
MODEL_ID = os.getenv("NOVITA_MODEL_ID", "meta-llama/llama-3.1-8b-instruct")
DB_PATH = os.getenv("YOE_LLM_CACHE_DB", "yoe_llm_cache.sqlite3")
PROMPT_VERSION = "yoe-required-v1"

MIN_SECONDS_BETWEEN_CALLS = float(os.getenv("YOE_LLM_MIN_SECONDS", "1.25"))
MAX_RETRIES = 6
_last_call_ts = 0.0

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

SYSTEM_TEMPLATE = """You are an information extraction assistant.
You MUST output only valid JSON. No markdown, no code fences, no explanations."""

USER_TEMPLATE = """Extract the minimum required PROFESSIONAL software engineering years of experience from this job posting.

Return strict JSON with exactly these keys:
1) "yoe_required": integer

Rules:
- Count only required professional work experience.
- Do not count education requirements as years of experience.
- Degree requirements alone always count as 0 years.
- A Bachelor's degree, Master's degree, PhD, or any degree requirement without an explicit professional years requirement means 0 years.
- If the posting says “Bachelor’s or Master’s degree” with no professional years requirement, output 0.
- If the posting says “Bachelor’s degree or equivalent practical experience” with no explicit number of professional years, output 0.
- If the posting says a degree OR a number of years of experience, treat the years as an alternative to education, not a required YOE amount. Output 0.
- Example: “Bachelor’s degree or 4+ years of relevant experience” → 0.
- Example: “Bachelor’s degree or equivalent practical experience” → 0.
- If the posting clearly requires professional experience regardless of education, count the stated minimum.
- Example: “4+ years of software engineering experience” → 4.
- Example: “Bachelor’s degree and 4+ years of software engineering experience” → 4.
- If the posting gives a range, output the lower bound.
- Example: “2-4 years” → 2.
- Example: “2 to 4 years” → 2.
- If the years of experience are listed as preferred, nice-to-have, a plus, desired, or optional, do not count them.
- If the posting says “new grad,” “entry level,” “university grad,” “recent graduate,” or “no experience required,” output 0.
- If no required professional YOE is clearly specified, output 0.
- Return only the required JSON object.

Company: {company}
Title: {title}

Job description:
{job_description}
"""

def _init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                cache_key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                created_utc TEXT NOT NULL
            )
            """
        )
        conn.commit()


_init_db()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_cache_key(model: str, prompt_version: str, company: str, title: str, jd: str) -> str:
    normalized = "\n".join([company.strip(), title.strip(), jd.strip()])
    return hashlib.sha256(
        f"{model}|{prompt_version}|{normalized}".encode("utf-8")
    ).hexdigest()


def _cache_get(cache_key: str) -> dict[str, Any] | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT value_json FROM cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def _cache_set(cache_key: str, value: dict[str, Any]) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache(cache_key, value_json, created_utc) VALUES(?,?,?)",
            (cache_key, json.dumps(value, ensure_ascii=False), _utc_now_iso()),
        )
        conn.commit()


def _throttle() -> None:
    global _last_call_ts
    now = time.time()
    wait = MIN_SECONDS_BETWEEN_CALLS - (now - _last_call_ts)
    if wait > 0:
        time.sleep(wait)
    _last_call_ts = time.time()


def _safe_json_loads(value: str) -> dict[str, Any]:
    try:
        return json.loads(value)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", value)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return {}


def _coerce_yoe(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, min(value, 50))
    if isinstance(value, float) and value.is_integer():
        return max(0, min(int(value), 50))
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return max(0, min(int(match.group()), 50))
    return 0


def _validate_output(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "yoe_required": _coerce_yoe(data.get("yoe_required", 0)),
        "extracted_time": "",
    }


def _call_llm(user_prompt: str, max_tokens: int) -> dict[str, Any]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _throttle()
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": SYSTEM_TEMPLATE},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=max_tokens,
            )
            raw = (response.choices[0].message.content or "").strip()
            return _safe_json_loads(raw)
        except RateLimitError:
            time.sleep(min(60, 2**attempt) + random.random())
        except (APITimeoutError, APIConnectionError, APIError):
            time.sleep(min(30, 2**attempt) + random.random())
        except Exception:
            time.sleep(min(20, 2**attempt) + random.random())

    return {}


def extract_yoe_requirement(company: str, title: str, job_description: str) -> dict[str, Any]:
    company = (company or "").strip()
    title = (title or "").strip()
    jd = str(job_description or "").strip()[:8000]

    if not jd:
        return {
            "yoe_required": 0,
            "extracted_time": _utc_now_iso(),
        }

    cache_key = _make_cache_key(MODEL_ID, PROMPT_VERSION, company, title, jd)
    cached = _cache_get(cache_key)
    if cached is not None:
        out = _validate_output(cached)
        out["extracted_time"] = cached.get("extracted_time") or _utc_now_iso()
        return out

    user_prompt = USER_TEMPLATE.format(
        company=company,
        title=title,
        job_description=jd,
    )

    validated = _validate_output(_call_llm(user_prompt, max_tokens=40))
    validated["extracted_time"] = _utc_now_iso()
    _cache_set(cache_key, validated)
    return validated

