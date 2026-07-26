# Function Traps

## Defaults and scope
- Defaults evaluate ONCE at `def` time: `def f(xs=[])` shares one list across all calls; `def f(t=time.time())` freezes the timestamp. Fix: `xs=None` + `if xs is None: xs = []`. The `xs = xs or []` shortcut is a bug: a caller passing an empty list to be filled in place gets a fresh list — their reference never sees the appends (canonical rule → SKILL.md rule 1).
- Assigning to a name anywhere in a function makes it local for the WHOLE function — reading it before the assignment raises `UnboundLocalError` even if a global exists. Declare `global` (module scope) or `nonlocal` (enclosing function) before writing.
- Closures capture variables, not values: `[lambda: i for i in range(3)]` all return 2 — every lambda reads the same `i` after the loop ends. Fix: `lambda i=i: i` (default binds now) or `functools.partial`.

## Decorators
- Always `@functools.wraps(fn)` on the wrapper — without it `__name__`, docstring, and signature introspection report the wrapper, breaking debuggers, pickling, and `mock.patch` targeting by name.
- `@deco` and `@deco()` are different call graphs: the first receives the function, the second must return something that receives the function. Support both only via an explicit `if fn is None` factory branch.
- `@functools.lru_cache` on a METHOD stores strong references to `self` in the cache — instances never free (memory leak in long-lived services). Use `functools.cached_property` (Python >=3.8) or cache on the instance. Default `maxsize=128`; `maxsize=None` grows without bound — size it deliberately.

## Generators
- A generator body does not run until first `next()` — argument validation inside the generator fires far from the call site. Split: a plain function validates, then returns the inner generator.
- Generators exhaust after one pass; a second `for` loop silently yields nothing. If consumed twice, materialize with `list()` or restructure — `itertools.tee` buffers everything the slower consumer hasn't read, so it is not a free replay.
- `return` inside `finally` swallows any in-flight exception from the `try` block — the function "succeeds" while the error vanishes. Same for `break`/`continue`; Python >=3.14 emits a SyntaxWarning for these (PEP 765).

## Signatures
- Force keyword-only for flags: `def move(src, dst, *, overwrite=False)` — prevents `move(a, b, True)` where True silently lands in the wrong positional slot after a refactor.
- After an except block, the exception variable is DELETED (`except Exception as e:` — using `e` after the block raises NameError). Bind to another name inside the block if needed later.
