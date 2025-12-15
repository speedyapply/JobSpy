# Repository Guidelines

## Project Structure & Module Organization

- `jobspy/`: core library package (one subpackage per job board, e.g. `jobspy/indeed/`, `jobspy/linkedin/`; shared logic in `jobspy/util.py`, data models in `jobspy/model.py`).
- `jobspy_cli.py`: command-line wrapper used for scripting/LLM integration.
- `tests/`: pytest tests (includes a few “live”/integration-style scripts such as `test_live_*`).
- `examples/`: small usage examples and snippets.
- Tooling/config: `pyproject.toml`, `poetry.lock`, `.pre-commit-config.yaml`, `.github/workflows/`.

## Build, Test, and Development Commands

This project uses Poetry for dependency management.

- `poetry install`: create/update the local virtualenv with project dependencies.
- `poetry run python jobspy_cli.py --search "python" --location "Remote"`: quick local smoke test of the CLI.
- `poetry run black .` (or `pre-commit run -a`): format code (Black, line length 88).
- `poetry build`: build the sdist/wheel (mirrors the publish workflow).
- `poetry run pytest -q`: run tests (if pytest isn’t in your env yet, add it via `poetry add --group dev pytest`).
- `docker compose -f docker-compose.test.yml up --build --abort-on-container-exit`: run the Flaresolverr-backed integration test container.

## Coding Style & Naming Conventions

- Formatting: Black (88 char lines). Prefer running via `pre-commit` before pushing.
- Python: use type hints where practical; keep scrapers isolated to their subpackage (`constant.py` for endpoints/headers, `util.py` for parsing/request logic).
- Naming: modules/functions in `snake_case`; tests in `tests/test_*.py`.

## Testing Guidelines

- Framework: pytest.
- Keep unit tests deterministic and fast; avoid adding new tests that hit real job boards by default.
- For changes that require live verification, add/extend scripts under `tests/` and document required env (e.g., `FLARESOLVERR_URL`).

## Commit & Pull Request Guidelines

- Commits follow a Conventional Commits-style pattern: `feat: ...`, `fix: ...`, `chore: ...`, optionally scoped (e.g., `fix(naukri): ...`).
- PRs should include: what changed, how to test (exact commands), and any scraper-specific notes (sample queries, expected fields, rate-limit/UA/proxy behavior). If output schema changes, update `README.md`/examples and tests.

## Security & Configuration Tips

- Do not commit credentials (proxy usernames/passwords, tokens). Prefer environment variables and local `.env`-style setup outside git.
- Scrapers are sensitive to headers/user agents and rate limiting; keep changes minimal and well-tested.

