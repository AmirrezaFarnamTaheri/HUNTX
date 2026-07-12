# HUNTX Hardening Audit — 2026-07-12

## Executive summary

This pass reviewed state persistence, ingestion concurrency, Telegram bot behavior,
MTProto client ownership, orchestration timeouts, CI trust boundaries, production
workflow behavior, generated-output lifecycle, and repository hygiene.

The immediate patch in PR #43 is intentionally limited to changes that can be
verified independently:

- enforce SQLite foreign keys on every connection;
- apply a 30-second SQLite busy timeout on every connection;
- prevent duplicate admin-triggered pipeline tasks;
- add regression tests for both behaviors;
- add a read-only branch and pull-request validation workflow.

The repository is approximately 1.7 GB. Generated artifacts committed by the
scheduled workflow are therefore treated as a reliability and maintainability
risk, not merely a cleanup concern.

## Verification performed

The following checks are executed by `.github/workflows/pr-validation.yml`:

1. hashed production dependency installation;
2. editable package installation without dependency drift;
3. Python bytecode compilation for `src` and `tests`;
4. fatal-error flake8 checks;
5. mypy over `src/huntx`;
6. the complete pytest suite.

The workflow has read-only repository permissions and is triggered for both pull
requests and hardening-branch pushes. The push trigger is required to bootstrap
validation before the workflow exists on the default branch.

## Findings fixed in PR #43

### H-01 — SQLite connection safety

**Risk:** concurrent workers could wait only on the driver timeout, while foreign
key constraints were not enabled consistently across independent connections.

**Fix:** every connection now applies:

```sql
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=30000;
```

The existing short-lived transaction and WAL model is preserved.

### H-02 — Duplicate admin pipeline execution

**Risk:** repeated `/admin run` commands or button presses could create multiple
background tasks. The filesystem lock prevented simultaneous execution but did
not prevent expensive tasks from queueing and producing confusing status
messages.

**Fix:** `AdminMixin` now stores the active task, rejects duplicate starts, and
clears the guard in `finally` after success or failure.

### H-03 — Missing pull-request validation

**Risk:** the production workflow ran only on schedule or manual dispatch, so
pull requests could be mergeable without compile, lint, type, or test evidence.

**Fix:** a separate least-privilege validation workflow now covers source,
configuration, scripts, tests, requirements, packaging metadata, and workflow
changes.

## Verified protections already present on main

- numeric-only administrator authorization;
- parameterized protocol-count inputs;
- recursive ZIP traversal and archive-bomb protections;
- required environment-variable expansion fails loudly;
- centralized proxy scheme definitions;
- Telegram publisher retry handling for rate limits;
- short-lived ingestion database transactions;
- schema migration tracking with `PRAGMA user_version`;
- raw-store orphan pruning;
- async ingestion workers with timeout cancellation.

## Unresolved critical and high-risk findings

### C-01 — MTProto client and lock ownership

Tracked in [issue #44](../issues/44).

`TelegramUserConnector.cleanup()` and `cleanup_async()` iterate over and clear all
thread-local clients, rather than only the client owned by the connector. A
connector can disconnect another active source, release the wrong session lock,
or leave its own lock held. Cleanup ownership must be explicit and idempotent.

### H-04 — Orchestrator timeout semantics

Tracked in [issue #45](../issues/45).

Publishing uses a `ThreadPoolExecutor` context manager. After a timeout from
`as_completed`, leaving the context waits for unfinished work by default. The
configured timeout is therefore not a reliable upper bound. Timeout outcomes are
also logged while the run can still report `COMPLETE` and return a normal summary.

### H-05 — Generated outputs committed to `main`

Tracked in [issue #46](../issues/46).

The scheduled workflow copies runtime outputs into the source tree and pushes
commits to `main`. This expands git history, requires write permissions, creates
push/rebase races, and couples data publication to source control. Runtime data
should move to Actions artifacts, object storage, Releases, or a dedicated data
branch/repository.

### H-06 — Bot callback and delivery hardening

Tracked in [issue #47](../issues/47).

Inline callbacks bypass command rate limiting; archive delivery does not reuse
the centralized filename matcher; persistent bot mode only warns when it shares
the ingestion token; cooldown state is unbounded; and delivery lacks explicit
FloodWait checkpoint behavior.

## Production workflow findings

The existing scheduled workflow should be redesigned in a separate pull request.
Combining that redesign with runtime changes would make rollback and review less
safe.

Confirmed concerns:

- production job has source-write and deployment permissions in one job;
- generated output is committed directly to the source branch;
- dependency retry can finish without an explicit final failure;
- pip cache key does not include `requirements.txt`;
- site data is generated more than once;
- state persistence is skipped when an earlier step fails;
- restore and persist safety policies are implicit rather than modeled as
  explicit job outputs and conditions;
- factory reset backs up the database but does not provide a complete,
  timestamped state-and-archive recovery point.

## Documentation and configuration findings

- README source and format counts should be derived from configuration or checked
  by tests to prevent drift.
- Runtime token requirements should distinguish bot ingestion, publication, and
  persistent interactive polling explicitly.
- Operational documentation should define partial-success behavior, timeout
  behavior, state restore guarantees, artifact retention, and disaster recovery.

## Recommended implementation order

1. Merge PR #43 only after all validation checks pass.
2. Fix MTProto ownership and lock lifecycle with dedicated concurrency tests.
3. Correct orchestrator timeout status and executor shutdown semantics.
4. Harden callback throttling, archive matching, token isolation, and FloodWait
   delivery behavior.
5. Replace source-branch output commits with artifact/object-storage publication.
6. Stop tracking generated output, then perform repository-history cleanup as a
   separately backed-up maintenance operation.
7. Add documentation drift checks and an operational recovery runbook.

## Merge gate for PR #43

PR #43 is ready only when all of the following are true:

- changed-file list contains only intentional files;
- compile, lint, mypy, and pytest all pass on the latest head SHA;
- no generated outputs or credentials are introduced;
- the pull-request description reflects the actual diff;
- unresolved architectural work remains linked to issues #44–#47.
