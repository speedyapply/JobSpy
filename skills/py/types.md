# Type Traps

## Identity vs equality
- CPython caches small ints (−5..256) and interns many string literals, so `x is y` on equal values often works by accident. Constant folding can even make `a = 257; b = 257; a is b` True in one file and False across modules — unreliable in BOTH directions. Rule: `is` only for `None`/`True`/`False`/sentinels.
- Sentinel pattern for "missing vs None": `_MISSING = object()` then `if x is _MISSING:` — the only object guaranteed distinct from every user value.
- `bool` subclasses `int`: `True == 1`, so `{1: "a", True: "b"}` has ONE key and `sum(flags)` counts Trues. When validating "is this an int", exclude bools explicitly: `isinstance(x, int) and not isinstance(x, bool)`.

## Floats and rounding
- Floats are IEEE-754 doubles: ~15-17 significant decimal digits; `0.1 + 0.2 == 0.30000000000000004`. Compare with `math.isclose(a, b)` (default `rel_tol=1e-09`); never `==` on computed floats.
- `round()` is banker's rounding (half to even): `round(0.5) == 0`, `round(1.5) == 2`, `round(2.5) == 2`. Invoices expecting half-up need `decimal` with `ROUND_HALF_UP`.
- `Decimal('0.1')` is exact; `Decimal(0.1)` is `0.1000000000000000055511151231257827...` — constructing from float imports the error. Same for `Fraction`.
- `float('nan') != float('nan')`, yet `nan in [nan]` is True — containers check identity before equality. NaN in data silently breaks sorting and deduplication; filter with `math.isnan` first.

## Strings
- `"filename.txt".strip(".txt")` strips a CHARACTER SET, not a suffix — returns `"filename"` sometimes, `"filenam"` for `"format.txt"`. Use `removesuffix`/`removeprefix` (Python >=3.9).
- Building strings with `+=` in a loop is O(n²); accumulate in a list and `''.join(parts)`.

## Hints and limits
- Type hints never enforce at runtime: `def f(x: int)` happily takes a string. Enforcement needs a checker (mypy/pyright) in CI or runtime validation (pydantic) at boundaries.
- `Any` vs `object`: `Any` silences the checker transitively (errors vanish downstream); `object` forces explicit narrowing before use. For "accepts anything, must be checked", annotate `object`.
- `Optional[X]` means `X | None` — nothing to do with the argument having a default. An arg can be optional without Optional, and required-but-nullable with it.
- `int` is arbitrary precision, but int↔str conversion beyond 4300 digits raises `ValueError` since Python >=3.11 (DoS fix, CVE-2020-10735); raise the limit with `sys.set_int_max_str_digits()` if you legitimately parse huge numbers.
- Chained comparisons bind as `and`: `a < b < c` is `(a < b) and (b < c)`. This also means `x == y in zs` chains — parenthesize anything mixing operators.
