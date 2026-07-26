# Collection Traps

## Aliasing and copies
- `[[]] * 3` creates 3 references to the SAME list — `m[0].append(1)` changes all rows. Build with `[[] for _ in range(3)]`.
- `a[:]`, `list(a)`, `dict(d)`, `.copy()` are all SHALLOW — nested objects stay shared. Nested structures need `copy.deepcopy`, but it is slow and follows every reference; for a known shape like dict-of-lists, `{k: v[:] for k, v in d.items()}` is the fast targeted copy.
- Mutating a dict key object after insertion (possible with custom `__hash__` on mutable state) makes the entry unfindable — lookup hashes the new state, the bucket holds the old. Keys must be effectively immutable.

## Ordering
- Dict preserves insertion order (guaranteed since Python >=3.7). Sets do NOT, and str hashing is salted per process (`PYTHONHASHSEED`) — set iteration order changes between runs. Never serialize set iteration order into golden files; `sorted()` first.
- `list.sort`/`sorted` are stable: for multi-key mixed-direction sorts, sort by the secondary key first, then the primary — or negate numeric keys in a single tuple key.
- `itertools.groupby` groups only CONSECUTIVE equal keys — on unsorted input it silently yields fragmented groups. Sort by the same key first, or use a dict accumulator.

## Lookup and mutation
- `d[k]` on a `defaultdict` INSERTS the key — logging `d[k]` or checking `if d[k]:` pollutes the dict. Membership tests must use `k in d`.
- `d.setdefault(k, expensive())` evaluates the default on every call, hit or miss. If the default is costly, use `defaultdict` or an explicit `in` check.
- `d.get(k)` returning None is ambiguous when None is a legal value — use a sentinel: `_MISSING = object()`, then `d.get(k, _MISSING) is _MISSING` distinguishes missing from None.
- Mutating while iterating: dicts raise `RuntimeError: dictionary changed size`, lists silently skip (removing index i shifts i+1 into i, loop moves to i+1). Iterate `list(xs)` or build a new collection.
- Slices never raise: `xs[10:20]` on a 3-element list returns `[]` — off-by-one bugs surface as empty results downstream, not as IndexError at the fault.

## Cost
- `x in list` is O(n). If you test membership against the same collection more than once, build a `set` once — the O(n) build amortizes immediately and each lookup drops to O(1).
- Top-k from n items when k << n: `heapq.nlargest(k, xs)` is O(n log k) vs full sort O(n log n) — matters from thousands of items up.
- `zip` silently truncates to the shortest input — misaligned data disappears instead of erroring. Pass `strict=True` (Python >=3.10) whenever inputs must be equal length.
