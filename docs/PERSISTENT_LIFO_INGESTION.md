# Persistent LIFO ingestion

HuntX processes MTProto (`telegram_user`) history as durable, non-overlapping UTC time windows. The default window is one hour and the default rolling horizon is 48 hours.

## Ordering contract

1. The newest incomplete hour is selected first.
2. Every eligible MTProto source is processed within that hour before an older hour may be claimed.
3. Sources rotate after each bounded page, so a dense channel cannot monopolize an hour.
4. New hours inserted by a later scheduled run preempt older residue because the queue is strict LIFO by `window_end_ts`.
5. Telegram Bot API sources remain live-only because `getUpdates` cannot retrieve historical channel messages.

The strict hour barrier intentionally prevents workers from descending into older history while the newest hour is leased or waiting for retry.

## Durable residue

Each source/hour pair is stored once in `ingestion_work_items` with a global uniqueness constraint:

```text
(source_id, window_start_ts, window_end_ts)
```

A work item stores its exclusive Telethon message-ID continuation cursor. After every bounded page, HuntX writes newly observed files and advances the residue cursor in the same SQLite transaction. A crash can therefore produce either:

- both the page data and its new cursor, or
- neither of them.

It cannot advance past data that was not committed.

Incomplete pages return to `partial` state and are available to the next worker or session. Claimed items use expiring leases. At startup, expired leases are recovered; at orderly shutdown, leases owned by the current run are returned to residue.

## Deduplication layers

HuntX uses independent idempotency layers:

- **Work deduplication:** one durable row per source/hour.
- **Observation deduplication:** `seen_files` enforces `UNIQUE(source_id, external_id)`.
- **Blob deduplication:** raw payloads are content-addressed by their hash.
- **Record/build deduplication:** build queries retain one active record per logical unique hash.

The window reader preserves the existing external-ID scheme (`message_id` for text and `message_id_media` for documents), so retries and migration from offset-based ingestion do not create duplicate observations.

## Runtime budget

The existing total run budget and completion buffer remain authoritative. By default:

- total application budget: 12,600 seconds (3.5 hours)
- completion buffer: 1,800 seconds (30 minutes)
- ingestion budget: 10,800 seconds (3 hours)

When the ingestion budget expires, workers stop claiming pages, release unfinished leases to residue, and continue through transform, build, publication, export, and durable-state persistence.

## Configuration

| Environment variable | Default | Meaning |
|---|---:|---|
| `HUNTX_LIFO_LOOKBACK_HOURS` | `file_fresh_hours` (normally `48`) | Rolling MTProto history horizon |
| `HUNTX_INGEST_WINDOW_SECONDS` | `3600` | Durable time-window size; bounded to 300 seconds through 24 hours |
| `HUNTX_INGEST_PAGE_SIZE` | `100` | Maximum messages scanned per source/window page; bounded to 10 through 1,000 |
| `HUNTX_SOURCE_TIMEOUT` | `600` | Maximum duration for one direct source or one MTProto page |
| `HUNTX_COMPLETION_BUFFER` | `1800` | Time reserved for downstream stages |

All boundaries and persisted timestamps are UTC epoch seconds. Telethon pages are read newest-to-oldest using exclusive `offset_date` and `offset_id` values.

## Operational fields

The final run summary includes:

- `lifo_campaign_id`
- `lifo_anchor_ts`
- `lifo_target_start_ts`
- `lifo_windows_seeded`
- `lifo_pages_processed`
- `lifo_windows_completed`
- `lifo_window_failures`
- `lifo_residue`

`lifo_residue.remaining` is the number of pending, partial, leased, or retry-wait work items that will survive for another session.
