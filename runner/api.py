"""The HTTP API the app talks to, with the searches running in the background.

  python api.py      serves on 0.0.0.0:$PORT (default 8000)

Environment, besides run.py's:
  PORT        port to listen on (default 8000)
  API_TOKEN   if set, every request needs the header "Authorization: Bearer <token>"

Endpoints (all JSON unless said otherwise):
  GET   /api/health             is it up, and is the token right
  GET   /api/jobs               ?list=recent|top|saved|applied|hidden|all
                                &q=words &offset=0 &limit=20 &days=7 (top only)
                                &min_match=0 &remote=1
  GET   /api/jobs/{id}          one job, with its description
  PATCH /api/jobs/{id}          {"saved": true, "applied": false, "hidden": false,
                                 "note": "text"}: any of them; returns the job
  GET   /api/stats              counts, by board, and the last and next run
  GET   /api/updates            ?after=ID &min_match=0: jobs stored after that id,
                                best first, and the newest id (for notifications)
  GET   /api/searches           the searches the server runs
  GET   /api/profile            the profile the compatibility score uses
  PUT   /api/profile            replace it; every stored job is scored again
  GET   /api/cv/info            your CV's name, size, date and the skills it names
  GET   /api/cv                 the CV file; ?format=base64 for {"name", "data"}
  PUT   /api/cv                 upload it: the PDF as the body, its name in the
                                X-Filename header (URL-encoded); or JSON
                                {"name": "cv.pdf", "data": "<base64>"}
  DELETE /api/cv                remove it
  GET   /api/export.csv         ?list=saved,applied: a CSV of those jobs
Nothing here sends a request to a job board: the app reads what the searches stored.
"""

from __future__ import annotations

import base64
import contextlib
import hmac
import json
import logging
import os
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote

import match
import run
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from store import LISTS, Store, to_json

log = logging.getLogger("runner.api")
VERSION = "1.0"
MAX_LIMIT = 100
store: Store | None = None


def db() -> Store:
    assert store is not None, "the store opens on startup"
    return store


def error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def int_param(request: Request, name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(request.query_params.get(name, default))
    except ValueError:
        raise ValueError(f"{name} must be a number") from None
    return max(low, min(high, value))


# endpoints


async def health(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "version": VERSION,
            "jobs": db().count(),
            "running": db().setting("running") == "1",
        }
    )


async def jobs(request: Request) -> JSONResponse:
    name = request.query_params.get("list", "recent")
    if name not in LISTS:
        return error(400, f"list must be one of {', '.join(LISTS)}")
    try:
        offset = int_param(request, "offset", 0, 0, 1_000_000)
        limit = int_param(request, "limit", 20, 1, MAX_LIMIT)
        days = int_param(request, "days", 7, 1, 365)
        min_match = int_param(request, "min_match", 0, 0, 100)
    except ValueError as e:
        return error(400, str(e))
    query = request.query_params.get("q", "").strip()
    remote = request.query_params.get("remote", "") in ("1", "true")
    rows, total = db().page(name, query, offset, limit, days, min_match, remote)
    return JSONResponse(
        {
            "list": name,
            "q": query,
            "total": total,
            "offset": offset,
            "limit": limit,
            "jobs": [to_json(row, description=False) for row in rows],
        }
    )


async def job(request: Request) -> JSONResponse:
    row = db().get(int(request.path_params["id"]))
    if row is None:
        return error(404, "no such job")
    return JSONResponse(to_json(row))


async def update_job(request: Request) -> JSONResponse:
    try:
        changes = await request.json()
    except ValueError:
        return error(400, "send a JSON object")
    if not isinstance(changes, dict) or not changes:
        return error(400, "send a JSON object")
    allowed = {"saved", "applied", "hidden", "note"}
    if unknown := set(changes) - allowed:
        return error(400, f"unknown fields: {', '.join(sorted(unknown))}")
    for flag in allowed - {"note"}:
        if flag in changes and not isinstance(changes[flag], bool):
            return error(400, f"{flag} must be true or false")
    if "note" in changes and not isinstance(changes["note"], (str, type(None))):
        return error(400, "note must be text or null")
    if isinstance(changes.get("note"), str) and len(changes["note"]) > 2000:
        return error(400, "note is longer than 2000 characters")
    job_id = int(request.path_params["id"])
    if not db().update(job_id, changes):
        return error(404, "no such job")
    row = db().get(job_id)
    assert row is not None
    return JSONResponse(to_json(row))


async def stats(request: Request) -> JSONResponse:
    store = db()
    try:
        last_result = json.loads(store.setting("last_run_result") or "null")
    except ValueError:
        last_result = None
    return JSONResponse(
        store.stats()
        | {
            "last_run": store.setting("last_run"),
            "last_run_result": last_result,
            "next_run": store.setting("next_run"),
            "running": store.setting("running") == "1",
            "interval_hours": run.INTERVAL_HOURS,
        }
    )


async def searches(request: Request) -> JSONResponse:
    try:
        return JSONResponse(run.load_searches())
    except (OSError, ValueError) as e:
        return error(500, str(e))


async def updates(request: Request) -> JSONResponse:
    try:
        after = int_param(request, "after", 0, 0, 10**12)
        min_match = int_param(request, "min_match", 0, 0, 100)
        limit = int_param(request, "limit", 50, 1, MAX_LIMIT)
    except ValueError as e:
        return error(400, str(e))
    rows, total, newest = db().updates(after, min_match, limit)
    return JSONResponse(
        {
            "after": after,
            "newest_id": newest,
            "total": total,
            "jobs": [to_json(row, description=False) for row in rows],
        }
    )


ENGLISH = ("", "A1", "A2", "B1", "B2", "C1", "C2")
PROFILE_LISTS = ("skills", "roles", "locations")


def read_profile() -> dict[str, object]:
    path = run.profile_path()
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {
        "skills": data.get("skills", []),
        "roles": data.get("roles", []),
        "years_experience": data.get("years_experience", 0),
        "locations": data.get("locations", []),
        "remote_ok": data.get("remote_ok", True),
        "english": str(data.get("english", "")).upper(),
    }


async def profile(request: Request) -> JSONResponse:
    try:
        return JSONResponse(read_profile())
    except ValueError as e:
        return error(500, f"profile.json: {e}")


def clean_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{name} must be a list of text")
    items = list(dict.fromkeys(v.strip().lower() for v in value if v.strip()))
    if len(items) > 200 or any(len(v) > 60 for v in items):
        raise ValueError(f"{name}: at most 200 items of 60 characters")
    return items


async def save_profile(request: Request) -> JSONResponse:
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError("send a JSON object")
        if unknown := set(data) - {
            *PROFILE_LISTS,
            "years_experience",
            "remote_ok",
            "english",
        }:
            raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
        profile = read_profile()
        for name in PROFILE_LISTS:
            if name in data:
                profile[name] = clean_list(data[name], name)
        if "years_experience" in data:
            years = data["years_experience"]
            if (
                isinstance(years, bool)
                or not isinstance(years, (int, float))
                or not 0 <= years <= 60
            ):
                raise ValueError("years_experience must be a number from 0 to 60")
            profile["years_experience"] = years
        if "remote_ok" in data:
            if not isinstance(data["remote_ok"], bool):
                raise ValueError("remote_ok must be true or false")
            profile["remote_ok"] = data["remote_ok"]
        if "english" in data:
            english = str(data["english"] or "").upper()
            if english not in ENGLISH:
                raise ValueError(
                    f"english must be one of {', '.join(e for e in ENGLISH if e)}"
                )
            profile["english"] = english
    except ValueError as e:
        return error(400, str(e))
    path = run.profile_path()
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    rescored = run.rescore_all(db())
    return JSONResponse(profile | {"rescored": rescored})


# the CV: the file in $DATA_DIR/cv.pdf, its details in cv.json

MAX_CV = 10 * 1024 * 1024


def cv_paths() -> tuple[Path, Path]:
    return run.DATA_DIR / "cv.pdf", run.DATA_DIR / "cv.json"


def cv_text(path: Path) -> str:
    try:
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    except Exception as e:  # a scanned or odd PDF: no text, still kept
        log.warning(f"cv: can't read its text: {e}")
        return ""


def cv_info_data() -> dict[str, object] | None:
    pdf, meta = cv_paths()
    if not pdf.exists():
        return None
    try:
        info = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        info = {
            "name": "cv.pdf",
            "size": pdf.stat().st_size,
            "uploaded_at": None,
            "skills": [],
        }
    have = {s.lower() for s in read_profile()["skills"]}  # type: ignore[attr-defined]
    info["suggested"] = [s for s in info.get("skills", []) if s.lower() not in have]
    return info


async def cv_info(request: Request) -> JSONResponse:
    info = cv_info_data()
    return JSONResponse(info) if info else error(404, "no CV uploaded")


async def cv_file(request: Request) -> Response:
    pdf, _ = cv_paths()
    if not pdf.exists():
        return error(404, "no CV uploaded")
    info = cv_info_data() or {}
    if request.query_params.get("format") == "base64":
        return JSONResponse(
            {
                "name": info.get("name") or "cv.pdf",
                "data": base64.b64encode(pdf.read_bytes()).decode(),
            }
        )
    name = quote(str(info.get("name") or "cv.pdf"))
    return Response(
        pdf.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{name}"},
    )


async def upload_cv(request: Request) -> JSONResponse:
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_CV * 4 // 3 + 1024:
            return error(413, "the CV is larger than 10 MB")
    name = unquote(request.headers.get("x-filename", "cv.pdf"))
    if "json" in request.headers.get("content-type", ""):
        try:
            sent = json.loads(body)
            name = str(sent.get("name") or "cv.pdf")
            body = base64.b64decode(str(sent["data"]), validate=True)
        except (ValueError, KeyError, TypeError, AttributeError):
            return error(400, 'send {"name": ..., "data": "<base64 of the PDF>"}')
    if len(body) > MAX_CV:
        return error(413, "the CV is larger than 10 MB")
    if not body.startswith(b"%PDF"):
        return error(400, "send the CV as a PDF")
    name = name.replace("/", "_").replace("\\", "_")[:120] or "cv.pdf"
    pdf, meta = cv_paths()
    pdf.parent.mkdir(parents=True, exist_ok=True)
    temp = pdf.with_suffix(".tmp")
    temp.write_bytes(body)
    temp.replace(pdf)
    skills = match.detect_skills(cv_text(pdf))
    meta.write_text(
        json.dumps(
            {
                "name": name,
                "size": len(body),
                "uploaded_at": datetime.now().isoformat(timespec="seconds"),
                "skills": skills,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return JSONResponse(cv_info_data())


async def delete_cv(request: Request) -> JSONResponse:
    for path in cv_paths():
        path.unlink(missing_ok=True)
    return JSONResponse({"deleted": True})


async def export(request: Request) -> Response:
    names = [
        n for n in request.query_params.get("list", "saved,applied").split(",") if n
    ]
    if not names or any(n not in LISTS for n in names):
        return error(400, f"list must be some of {', '.join(LISTS)}")
    csv = db().export(names).to_csv(index=False)
    return Response(
        csv.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ofertas.csv"'},
    )


# the token, checked on every /api request but the CORS preflight


class TokenMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, object],
        receive: Callable[..., Awaitable[object]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        token = os.environ.get("API_TOKEN", "")
        if token and scope["type"] == "http" and scope.get("method") != "OPTIONS":
            headers = dict(scope.get("headers") or [])  # type: ignore[arg-type]
            given = headers.get(b"authorization", b"").decode()
            if not hmac.compare_digest(given, f"Bearer {token}"):
                await error(401, "wrong or missing token")(scope, receive, send)  # type: ignore[arg-type]
                return
        await self.app(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    global store
    store = run.open_store()
    stop = threading.Event()
    searcher = threading.Thread(
        target=run.loop, args=(store, stop), name="searches", daemon=True
    )
    if os.environ.get("SEARCHES_ENABLED", "1") != "0":
        searcher.start()
    else:
        log.info("SEARCHES_ENABLED=0: serving the stored jobs only")
    yield
    stop.set()


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/api/health", health),
            Route("/api/jobs", jobs),
            Route("/api/jobs/{id:int}", job, methods=["GET"]),
            Route("/api/jobs/{id:int}", update_job, methods=["PATCH"]),
            Route("/api/stats", stats),
            Route("/api/searches", searches),
            Route("/api/updates", updates),
            Route("/api/profile", profile, methods=["GET"]),
            Route("/api/profile", save_profile, methods=["PUT"]),
            Route("/api/cv/info", cv_info),
            Route("/api/cv", cv_file, methods=["GET"]),
            Route("/api/cv", upload_cv, methods=["PUT"]),
            Route("/api/cv", delete_cv, methods=["DELETE"]),
            Route("/api/export.csv", export),
        ],
        middleware=[
            # the app runs from capacitor://localhost or https://localhost; Tailscale
            # keeps strangers out, API_TOKEN keeps out the rest of your tailnet
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["GET", "PATCH", "PUT", "DELETE", "OPTIONS"],
                allow_headers=["Authorization", "Content-Type", "X-Filename"],
                expose_headers=["Content-Disposition"],
            ),
            Middleware(TokenMiddleware),
        ],
        lifespan=lifespan,
    )


app = create_app()


def main() -> None:
    import uvicorn

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if not os.environ.get("API_TOKEN"):
        log.warning("API_TOKEN isn't set: anyone on your tailnet can use the API")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
