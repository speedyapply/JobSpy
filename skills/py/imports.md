# Import Traps

## Circular imports — fix in this order
1. Switch `from a import f` to `import a` and call `a.f()` — module-level attribute access resolves at CALL time, after both modules finish loading. Cheapest fix, often sufficient.
2. Type-only cycle? Move the import under `if TYPE_CHECKING:` and use string annotations (or `from __future__ import annotations`) — zero runtime import.
3. Move the import inside the function that needs it — defers execution past the cycle. Works, but hides the dependency; leave a comment naming the cycle.
4. Still cyclic → the design is telling you two modules share a concept: extract it into a third module both import.

Symptom signature: `ImportError: cannot import name X from partially initialized module` — the traceback names both ends of the cycle; read it before restructuring.

## Binding semantics
- `from x import name` COPIES the binding at import time. Reassigning `x.name` later (monkeypatching, reload, config injection) is invisible to every module that did `from`-import — this is also why `mock.patch` must target the module where the name is USED, not where it is defined.
- Modules are cached in `sys.modules`: second import is a dict lookup, side effects run once. `importlib.reload` re-executes the module but every existing `from`-imported reference still points at the old objects — reload is for interactive sessions, not production.

## Layout and shadowing
- A local file named like a stdlib/dependency module (`email.py`, `json.py`, `token.py`, `test.py`) shadows the real one — symptom is a cryptic `AttributeError: module 'json' has no attribute 'loads'`. Diagnose with `import json; print(json.__file__)`; rename your file.
- `python script.py` puts the SCRIPT'S directory at `sys.path[0]`; `python -m pkg.mod` puts the current directory and enables relative imports. Relative imports (`from . import x`) fail with "attempted relative import" when the file runs as a script — run modules with `-m` from the project root.
- A missing `__init__.py` creates an implicit namespace package: same-named directories on `sys.path` silently MERGE, and tools may import a half-tree. Regular packages: always ship `__init__.py`.
- `__init__.py` executes on ANY import from the package — heavy imports or side effects there tax every consumer and are the most common hidden cycle edge. Keep it to re-exports, or empty.
- Top-level module code runs on import — and again in every multiprocessing spawn child. Entry-point logic goes under `if __name__ == "__main__":` (canonical rule → SKILL.md rule 9).
- Mutating `sys.path` at runtime affects every subsequent import process-wide and breaks under test runners with their own path setup — fix packaging (editable install) instead.
