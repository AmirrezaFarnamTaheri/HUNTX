# Persistent LIFO ingestion

HuntX processes MTProto (`telegram_user`) history as durable, non-overlapping UTC time windows. The default window is one hour and the default rolling horizon is 48 hours.

## Window boundary contract

Every window is half-open: `[window_start_ts, window_end_ts)`. A message exactly at the start belongs to that window; a message exactly at the end belongs to the next newer window. Boundaries are aligned using UTC epoch seconds, so daylight-saving changes do not affect partitioning.

The newest window ends at the next aligned boundary. It therefore includes the current partial hour and may have an end timestamp in the near future. Telethon is queried newest-to-oldest with exclusive `offset_date=window_end_ts`; messages with timestamps at or beyond the end are ignored defensively. The lower boundary is enforced in application code.

Continuation uses exclusive `offset_id`. When a page ends on message ID `N`, the residue cursor is `N`, and the next page starts with messages older than `N`. This prevents the boundary message from being replayed.

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

### Crash and lease states

- **Crash before the page transaction begins:** the row remains `leased`; the next session recovers it after lease expiry.
- **Crash during the transaction:** SQLite rolls back both observations and cursor advancement; the recovered item safely replays the uncommitted page.
- **Crash after commit but before process shutdown:** observations and cursor are both durable; the expired lease is recovered from the committed `partial` or `completed` state.
- **Slow valid request:** workers do not reclaim leased rows during the same run. Recovery runs only at startup, and the repository process lock prevents concurrent HuntX sessions from sharing the state database. Lease duration is the page timeout plus a safety margin.

Lease timestamps use the host's UTC epoch clock. Large backwards clock corrections can delay recovery; large forward corrections can make a lease appear expired at the next startup. Idempotent observation IDs and atomic cursor checkpoints keep either case safe, though operators should keep runner clocks synchronized.

## Deduplication layers

HuntX uses independent idempotency layers:

- **Work deduplication:** one durable row per source/hour.
- **Observation deduplication:** `seen_files` enforces `UNIQUE(source_id, external_id)`.
- **Blob deduplication:** raw payloads are content-addressed by their hash.
- **Record/build deduplication:** build queries retain one active record per logical unique hash.

The window reader preserves the existing external-ID scheme (`message_id` for text and `message_id_media` for documents), so retries and migration from offset-based ingestion do not create duplicate observations.

## Schema migration and rollback

No manual migration command is required. `DBConnection` applies `schema.sql` at startup with `CREATE TABLE IF NOT EXISTS`, creating the campaign and work-item tables alongside the existing state tables. Existing `source_state` offsets, `seen_files`, records, and publication history are retained.

On first execution, the queue seeds source/hour work rows for the configured horizon. Existing observations are skipped by the current `seen_files` uniqueness constraint, making the transition from source offsets idempotent.

Rolling back the application code does not require dropping the new tables: older code ignores them. To remove the scheduler state after rollback, operators may back up the database and drop only `ingestion_work_items` and `ingestion_campaigns`; existing observations and source offsets remain independent.

## Runtime budget

The existing total run budget and completion buffer remain authoritative. By default:

- total application budget: 12,600 seconds (3.5 hours)
- completion buffer: 1,800 seconds (30 minutes)
- ingestion budget: 10,800 seconds (3 hours)

When the ingestion budget expires, workers stop claiming pages, release unfinished leases to residue, and continue through transform, build, publication, export, and durable-state persistence.

## Configuration

| Environment variable | Default | Recommended use |
|---|---:|---|
| `HUNTX_LIFO_LOOKBACK_HOURS` | `file_fresh_hours` (normally `48`) | Keep at `48` for the production acquisition horizon; raise only with a larger durable-state budget |
| `HUNTX_INGEST_WINDOW_SECONDS` | `3600` | One hour balances fairness and queue size; reduce for exceptionally dense channels |
| `HUNTX_INGEST_PAGE_SIZE` | `100` | Increase moderately for sparse channels; smaller pages checkpoint more often |
| `HUNTX_SOURCE_TIMEOUT` | `600` | Maximum duration for one direct source or one MTProto page |
| `HUNTX_COMPLETION_BUFFER` | `1800` | Keep enough time for transform, build, publication, export, and state persistence |

`HUNTX_INGEST_WINDOW_SECONDS` is bounded to 300 seconds through 24 hours. `HUNTX_INGEST_PAGE_SIZE` is bounded to 10 through 1,000. All boundaries and persisted timestamps are UTC epoch seconds.

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
