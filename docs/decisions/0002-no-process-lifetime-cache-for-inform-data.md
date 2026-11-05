---
status: proposed  # accepted once PR #5 merges
date: 2026-10-06
decision-makers: ["@zackarno"]
consulted: []
informed: OCHA CHD Data Science team
---

# Read the INFORM parquet on every session rather than caching it for the process

## Context and Problem Statement

`load_inform()` was wrapped in `@lru_cache(maxsize=1)`. `marimo run` serves
every visitor as a thread in one long-lived process, so the cache was shared by
everyone and only cleared when App Service restarted. The weekly refresh
(ADR 0001) could update the blob and the live app would keep serving whatever
it loaded at startup, indefinitely.

## Considered Options

* **A — No cache.** Each session reads the parquet from blob.
* **B — Time-limited cache** (TTL).
* **C — ETag check** on each call, re-read only when the blob changed.
* **D — Restart the App Service from the refresh workflow.**

## Decision Outcome

Chosen: **A** (PR #5).

* B — rejected: stale for up to the TTL, plus a lock, module state and a
  setting to tune, for a 130 KB file.
* C — rejected: still a network round trip per session, more code, and a
  second failure path to reason about.
* D — rejected: needs Azure credentials in Actions. The publish profile can
  deploy but cannot restart.

A is also the fail-loudly choice: an expired SAS surfaces as an error at session
start instead of the app serving old data forever.

### Consequences

* Good, because a refresh is visible to the next visitor with no restart.
* Bad, because session start costs about 0.6 s more. Session start already reads
  the 3RM xlsx from blob uncached, so this is the same kind of cost, not a new
  one. If it ever matters, B is the fallback.

## More Information

* PR #5; `src/datasets/inform.py`.
