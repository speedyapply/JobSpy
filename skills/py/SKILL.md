---
name: py
slug: py
version: 1.0.2
changelog: Deeper idioms, gotchas, and performance guidance
description: >-
  Avoids Python runtime traps — mutable defaults, is vs ==, GIL, asyncio pitfalls,
  circular imports, mock patching. Use when writing, reviewing, or debugging Python code.
homepage: https://clawic.com/skills/py
metadata:
  clawdbot:
    emoji: 🐍
    requires:
      bins:
      - python3
    os:
    - linux
    - darwin
    - win32
    displayName: Python
---

## When To Use

- Writing or reviewing Python — scan Core Rules before committing
- Debugging wrong results without exceptions: state leaking across calls, aliased mutations, silent truncation
- Choosing a concurrency model (threads vs asyncio vs multiprocessing)
- Fixing ImportError, circular imports, or "works here, fails there" module issues
- Writing pytest suites with mocks, fixtures, or async tests
- Not for library-specific issues — `pandas`, `numpy`, `fastapi` have their own skills

## Quick Reference

| Situation | Read |
|-----------|------|
| Equality/value surprises: `is` vs `==`, floats, `round`, bool-as-int | `types.md` |
| Data structure bugs: aliasing, copies, ordering, membership cost | `collections.md` |
| State leaks across calls, closures, decorators, generators | `functions.md` |
| Class design: shared attributes, hashability, MRO, `__slots__` | `classes.md` |
| Slow, hanging, or racy: GIL, threads, asyncio, multiprocessing | `concurrency.md` |
| Circular imports, module shadowing, package layout | `imports.md` |
| Tests pass but shouldn't: mock patching, fixtures, async tests | `testing.md` |
| Anything else | Core Rules below, then general Python knowledge |

## Core Rules

1. No mutable defaults: `def f(xs=None)` then `if xs is None: xs = []`. Never `xs = xs or []` — a caller passing an empty list to be filled gets a fresh list instead; their reference stays empty.
2. `is` only for `None`, `True`, `False`, and sentinel objects; `==` for everything else. Interning makes `is` on ints/strings pass in tests and fail in production (`types.md`).
3. Never mutate the collection you iterate — dicts raise `RuntimeError`, lists silently skip elements. Iterate a copy (`for x in list(xs)`) or collect changes and apply after.
4. Match concurrency to workload: pure-Python CPU → `multiprocessing`; I/O → threads or asyncio; threads never speed up pure-Python CPU work — the GIL serializes bytecode (`concurrency.md`).
5. `except Exception:`, never bare `except:` — bare also catches `KeyboardInterrupt` and `SystemExit`, making the process unkillable. Re-raise with bare `raise`, keeping the original traceback.
6. Files, locks, sockets: always `with`. CPython's refcounting closes leaked handles by accident; exceptions and other interpreters (PyPy) expose the leak.
7. Money and exact decimals: `decimal.Decimal('1.10')` from strings — `Decimal(1.1)` imports the float error it was meant to avoid. Float comparisons via `math.isclose` (`types.md`).
8. Declare `encoding='utf-8'` at every I/O boundary — the default follows the platform locale until UTF-8 becomes the default (PEP 686, Python 3.15), so code breaks first on Windows.
9. Guard entry points with `if __name__ == "__main__":` — top-level code runs on every import and again in every `multiprocessing` spawn (`imports.md`).

## Related Skills

More Clawic skills, get them at https://clawic.com/skills/py (install if the user confirms):
- `pandas` — DataFrame-specific traps and idioms
- `fastapi` — async web APIs in Python
- `django` — Django ORM and framework patterns
- `profiling` — when the question is "why is it slow", measure first
- `debugging` — general fault-isolation strategy beyond Python specifics

## Feedback

- If useful, star it: https://clawic.com/skills/py
- Latest version: https://clawic.com/skills/py

Part of [Clawic](https://clawic.com), the verified skill library. Get this skill: https://clawic.com/skills/py.
