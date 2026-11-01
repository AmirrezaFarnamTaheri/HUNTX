# HuntX Run Health and Resilience Contract

HuntX production runs use three dispositions: `success`, `degraded`, and `fatal`.
The disposition describes whether useful, trustworthy progress can be retained. It is intentionally separate from the availability of any one external source or delivery destination.

## Dispositions

### `success`

The bounded pipeline completed without known degradation. Sources, builds, exports, and configured publication work reached their expected terminal states.

### `degraded`

Useful work or a verified checkpoint exists, but one or more isolated operations did not complete. A degraded run exits successfully so GitHub Actions can persist state and publish independently verified output.

Typical degraded reasons include:

- one or more sources are unavailable, private, removed, rate-limited, or timed out;
- ingestion reached its bounded time budget and left persistent queue residue;
- one or more routes or Telegram publication attempts failed;
- publication work was pending or cancelled when the deadline expired;
- cleanup or post-run delivery failed after durable output was created;
- no new artifact was generated, but existing state remains valid;
- the outer watchdog interrupted execution after recoverable progress and a verified checkpoint exists.

A degraded disposition does **not** make an unverified artifact publishable. Packaging and deployment have their own independent verification gate.

### `fatal`

The run cannot safely claim a recoverable outcome. Fatal examples include:

- invalid production configuration;
- no approved/configured sources;
- state corruption or an unrecoverable state invariant;
- a security or integrity violation;
- an unknown terminal status with no recoverable progress;
- a deadline or unhandled execution failure before any trustworthy progress;
- inability to validate and package the runtime checkpoint.

Fatal dispositions remain red and block successful completion.

## Independent safety gates

The production workflow separates four concerns:

1. **Runtime health** — classifies the run as success, degraded, or fatal.
2. **Checkpoint integrity** — validates the state database and raw-store references, builds an immutable generation, and verifies its manifest.
3. **Release packaging** — verifies output content and materializes Pages data.
4. **External delivery** — attempts publication without controlling whether durable local work is retained.

A source or Telegram delivery failure can degrade runtime health without invalidating the checkpoint. Conversely, a zero exit code cannot override a `fatal` structured disposition.

## Last-known-good release safenet

Before execution, the workflow snapshots the restored verified `outputs` and `outputs_dev` directories.

After execution:

1. The current output is independently verified and materialized.
2. If current output fails verification or materialization, the workflow restores the snapshot.
3. The restored output is independently verified again before it can be packaged or deployed.
4. If neither candidate verifies, no release artifact or Pages deployment is produced; the verified checkpoint and diagnostics can still persist.

The `package_source` field reports:

- `current` — this run's output passed verification;
- `restored` — the last-known-good output was reverified and used;
- `none` — no independently verified release candidate was available.

This prevents a partial run from replacing a known-good release with malformed or incomplete output.

## Structured diagnostics

The CLI writes an atomic JSON envelope to `HUNTX_RUN_SUMMARY_PATH` and emits the same information as a single log record:

```text
HUNTX_RUN_HEALTH={...}
```

Schema version 1 includes:

- `disposition` and raw runtime `status`;
- ordered `reasons`;
- `recoverable_progress`;
- normalized `metrics`;
- the original orchestrator `summary`.

Important metrics include source successes/failures, route failures, publication attempts/failures/pending/cancelled work, build and ingestion cancellations, LIFO pages/windows/residue, budget-skipped ingestion, cleanup/export failures, post-run delivery failures, and timeout stage.

The Actions reporter also emits:

- a GitHub notice, warning, or error annotation;
- a `HUNTX_RUNTIME_DIAGNOSTICS_BEGIN`/`END` block;
- a job-summary metrics table and reason list;
- checkpoint/package readiness and package source;
- an artifact inventory capped at 200 entries;
- uploaded runtime, environment, and JSON diagnostic artifacts.

## Examples

### Degraded run

```json
{
  "disposition": "degraded",
  "status": "partial",
  "reasons": [
    "partial_run",
    "source_failures",
    "publish_failures",
    "all_publish_attempts_failed"
  ],
  "recoverable_progress": true,
  "metrics": {
    "total_artifacts": 4,
    "ingest_ok": 67,
    "ingest_err": 8,
    "publish_attempts": 4,
    "publish_failures": 4
  }
}
```

Expected workflow behavior:

- checkpoint is validated and persisted;
- current output is verified, or the last-known-good release safenet is attempted;
- external delivery failures remain visible but do not discard durable work;
- the run is green with warning annotations.

### Fatal run

```json
{
  "disposition": "fatal",
  "status": "failed",
  "reasons": ["no_approved_sources"],
  "recoverable_progress": false,
  "metrics": {
    "total_artifacts": 0,
    "ingest_ok": 0,
    "ingest_err": 0
  }
}
```

Expected workflow behavior:

- no runtime success is reported;
- the fatal disposition wins even if a wrapper process accidentally exits zero;
- the workflow fails red;
- diagnostics are still uploaded when available.

## Operating principle

Partial external availability is normal for an aggregation system. HuntX therefore preserves verified progress and exposes degradation precisely. It fails hard only when configuration, integrity, safety, or the absence of recoverable progress makes continuation untrustworthy.
