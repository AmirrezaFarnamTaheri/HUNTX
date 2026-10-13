# Source-health reporting

HUNTX records upstream **retrieval and ingestion health**, separately from proxy
authentication, reachability, latency, or fitness to use. A successfully fetched
subscription is **not** evidence that any proxy inside it works.

## Where to find the results

Every production run writes `persist/data/logs/source-health.json`. GitHub
Actions uploads it with the `huntx-logs-<run-id>-<attempt>` diagnostics artifact
(7-day retention), and separately as `source-health-<run-id>-<attempt>`
(30-day retention) for comparing source outcomes across runs. The job summary shows aggregate counts. Per-source HTTP
retrieval history persists in the protected SQLite runtime checkpoint; Telegram
window outcomes persist in `ingestion_work_items`.

To inspect a completed production run, download its **huntx-logs** artifact and
open `source-health.json`. This contains source IDs, types, approval status,
HTTP reliability aggregates, and Telegram campaign window counts. It does not
contain upstream URLs, query parameters, credentials, sessions, or raw error
messages.

## Status semantics

- `retrieved`: the HTTPS feed was fetched, its payload parsed/audited, and
  syntax validated; no proxy-protocol authentication was performed.
- `source_failure`: an actual HTTP feed retrieval or parsing attempt failed.
  Such events count toward that feed's failure streak and rolling Wilson bound.
- `infrastructure_error`: HUNTX could not run the local feed-fetch worker.
  No conclusion can be drawn about the upstream feed. This **does not** increment
  source failure counters or add a negative retrieval sample.
- `observed`: a Telegram source has completed windows in the current ingestion
  campaign (possibly with zero new messages).
- `retrying` or `quarantined`: the current Telegram campaign has retryable or
  terminal window failures; the source is not assumed to be a dead proxy.
- `not_observed`: no source-specific evidence was available in the current
  campaign, not a definitive failure.
- `evidence_unavailable`: the current campaign's queue could not be read.
- `disabled`: intentionally outside production ingestion due to configuration
  or source trust policy.

Telegram windows are scoped by `lifo_campaign_id`, not by lifetime totals.
HTTP rolling observations are bounded, historical, and originate from the
protected state checkpoint. Historical HTTP failure counters preceding the
2026-10-13 Go-worker fix may include incorrectly attributed local worker errors;
do not use those older counts alone to retire any source.

## Debugging degraded health

1. Check the production `source-health.json` and job summary.
2. If `http_infrastructure_errors` is nonzero, inspect the Go worker provisioned
   in the **ingest-build-package** job; do not retire affected feeds.
3. For `source_failure`, inspect the source ID, error class, failure streak,
   last successful retrieval, and recent availability evidence. Check a sequence
   of runs rather than a one-off transient failure.
4. For Telegram `retrying`/`quarantined`, inspect the current campaign and
   sanitized logs; avoid treating a duplicated canonical channel or zero
   messages as transport failure.
5. Only change source trust or retirement status with separate, validated
   evidence and review. The tracker never auto-removes sources.

The reporter can be reproduced from an intact runtime state and health summary:

```bash
python scripts/report_source_health.py \
  --config configs/config.prod.yaml \
  --summary persist/data/logs/run-summary.json \
  --db persist/state.db \
  --output persist/data/logs/source-health.json
```
