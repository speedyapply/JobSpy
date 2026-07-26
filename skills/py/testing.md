# Testing Traps

## Mocking
- Patch where the name is USED, not where it is defined: `views.py` does `from utils import now` → `mock.patch('app.views.now')`, not `'app.utils.now'`. The `from`-import copied the binding at import time; patching the origin changes an object nobody reads.
- A plain `Mock` accepts ANY attribute: `m.called_once()` (missing `assert_` prefix) returns a truthy Mock and the test passes while asserting nothing. Mock guards misspellings starting with `assert`/`assret` (raises AttributeError), but not this one. Defense: `autospec=True` everywhere — it also fails the test when the real signature drifts, which plain Mock lets refactors slip past.
- Mock state persists across a test if shared (module-level mock, class-scoped patch): call counts accumulate and test B passes because test A ran. Prefer function-scoped `mock.patch` as decorator/context manager; `reset_mock()` is the last resort, not the design.
- `datetime.datetime` is a C type — you cannot patch `.now` on it. Patch the module reference where used (`mock.patch('app.views.datetime')`) or, better, inject a clock function so tests pass a fake.

## Pytest
- `pytest.raises(Exception)` proves almost nothing — any bug raises something. Always the narrowest exception plus `match="..."` (regex) so the wrong error at the right place still fails.
- Fixture scope: `function` (default) rebuilds per test; `module`/`session` share ONE object — a mutable session fixture creates order-dependent tests that fail only in full runs. Session scope is for expensive immutable setup (DB schema, compiled artifacts) only.
- Fixture teardown belongs after `yield` in the fixture body — code after `return` never runs, and teardown after a failed test runs only with the yield pattern.
- Float assertions: `assert total == 0.3` fails on binary float arithmetic; use `pytest.approx(0.3)` — default relative tolerance 1e-6.
- An `async def` test without a plugin is not executed — pytest warns and the assertions never run, which reads as green in a quick scan. Install `pytest-asyncio` and mark tests (or set `asyncio_mode = auto`).
- Parametrize over copy-pasted test functions once you have 3+ input/expected pairs — `@pytest.mark.parametrize` with `ids=` makes each case its own failure line.

## Semantics
- `assert` disappears under `python -O` — never use it for runtime validation in production code (raise explicitly). In tests it is fine: pytest rewrites asserts and does not run optimized.
- A test you never saw fail proves nothing: run the failing test BEFORE writing the fix; red→green is the evidence the test guards the bug. Workflow: `pytest -x --lf` reruns last failures first.
