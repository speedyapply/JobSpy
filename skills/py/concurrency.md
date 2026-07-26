# Concurrency Traps

## Choosing a model

| Workload | Use |
|----------|-----|
| Pure-Python CPU-bound | `multiprocessing` / `ProcessPoolExecutor` (only escape from the GIL) |
| CPU-bound inside numpy/C extensions | Threads are fine — C code releases the GIL |
| I/O-bound, blocking libraries (requests, DB drivers) | `ThreadPoolExecutor` |
| I/O-bound, very high concurrency, async-native libraries end to end | asyncio |
| Unsure | `ThreadPoolExecutor` — simplest model that is correct for I/O; one blocking call can't freeze siblings |

Contrarian but defensible: asyncio is not "faster Python" — for moderate I/O concurrency, threads match it with far less ceremony. asyncio pays off when connection counts are high AND the whole stack is async; one blocking driver in the chain forfeits the benefit.

## GIL and threads
- The GIL lets one thread execute bytecode at a time, switching every ~5 ms by default (`sys.getswitchinterval()` → 0.005). Threads give zero speedup on pure-Python CPU work — they add switching overhead instead.
- Python >=3.13 ships an experimental free-threaded (no-GIL) build as a separate binary; do not design production code around it yet.
- The GIL does NOT make compound operations atomic: `x += 1` is read-modify-write and loses updates under contention. Guard shared mutable state with `threading.Lock`, or avoid sharing — hand off via `queue.Queue`.
- `ThreadPoolExecutor` default is `min(32, os.cpu_count() + 4)` workers — sized for I/O. An executor future's exception surfaces only when you call `.result()`; fire-and-forget means errors vanish. Iterate `as_completed` or check results.
- Daemon threads die at interpreter exit with NO cleanup — `finally` blocks and context managers do not run. Never let a daemon thread hold files, locks, or half-written state.

## Multiprocessing
- Start method: Windows and macOS (Python >=3.8) use spawn; Linux switches its default from fork to forkserver in Python >=3.14 (fork + threads deadlocks). Spawn RE-IMPORTS your module in each child: unguarded top-level code re-executes — the classic infinite-spawn crash. Always `if __name__ == "__main__":` (SKILL.md rule 9).
- Everything crossing the process boundary must pickle: lambdas, local functions, open handles, and live connections fail — sometimes only on spawn platforms, so "works on my Linux box" is not evidence.

## Asyncio
- A forgotten `await` returns a coroutine object that never runs; the "never awaited" warning appears only at garbage collection, far from the bug. Treat any unused coroutine value as an error.
- Blocking calls (`time.sleep`, `requests`, heavy CPU) freeze the entire event loop — every task stalls. Use `asyncio.sleep`, async clients, or `await asyncio.to_thread(blocking_fn)` (Python >=3.9).
- KEEP a reference to `asyncio.create_task(...)` results — the loop holds only weak references, and an unreferenced task can be garbage-collected mid-execution. Store tasks in a set, or use `asyncio.TaskGroup` (Python >=3.11), which also cancels siblings on first failure — structured, unlike bare `gather`.
- `asyncio.gather(..., return_exceptions=True)` converts failures into return VALUES — if you don't isinstance-check the results, errors pass silently as list elements.
- `asyncio.run()` inside a running loop raises — in notebooks and async frameworks a loop already runs; `await` directly or `create_task`.
