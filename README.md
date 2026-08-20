# HUNTX

HUNTX is a governed proxy-configuration aggregation system. It ingests public Telegram source material, stores raw observations durably, parses supported configuration formats, builds deduplicated route artifacts, publishes changed artifacts to configured Telegram destinations, and optionally delivers selected outputs through the approval-gated **GatherX** bot.

The production deployment in this repository is a **single Python application plus a GitHub Actions control plane**, not a microservice fleet. The current production configuration uses 85 MTProto (`telegram_user`) sources, one `all_sources` publication route, and 12 configured output formats.

## What is implemented

- **Governed production runtime** — every supported run entrypoint delegates to one runtime service and `create_production_orchestrator()`.
- **Durable newest-first MTProto ingestion** — SQLite-backed rolling-window work items, leases, continuation cursors, retry state, source revocation, and bounded deadlines.
- **Alternative source connectors** — Telegram Bot API and the Go V2Ray collector are implemented but are not used by the current production configuration.
- **Content-addressed raw storage** — source bytes are stored by SHA-256 digest and revalidated on read.
- **SQLite state** — source state, observations, normalized records, ingestion work, publication intents/deliveries, bot inbox state, GatherX users, and delivery checkpoints.
- **Format routing and transformation** — extension/content detection plus registered format handlers.
- **Protocol-aware proxy validation** — `npvt` and `npvtsub` share the same validation/canonicalization boundary before records can be built back into subscriptions.
- **Governed build policy** — route source membership and publication tier are enforced before artifact construction.
- **Derived proxy artifacts** — decoded JSON, base64 subscriptions, and sing-box output where a faithful mapping exists.
- **Ledgered Telegram publication** — per-destination intent/delivery state prevents blind replay after ambiguous or partial outcomes.
- **GatherX private bot** — pending registration, operator approval, approved-only downloads/settings, admin-only operational controls, mute/unmute, and resumable per-user delivery.
- **Structured runtime health** — success/degraded/fatal classification plus machine-readable run summaries used by CI investigation gates.
- **Immutable production checkpointing** — GitHub Actions can restore and persist verified generations in S3 when configured; otherwise runs are intentionally stateless between hosted runners.
- **Verified static publication** — production output is verified, packaged for GitHub Pages, and also published through the generated-output workflow.
- **Go release tools** — `huntx-tools` verifies outputs, builds/verifies runtime generations, and generates site data. `huntx-engine` is a standalone parse/benchmark/georoute/healing CLI; it is built and tested but is not the Python production execution engine.

## Quick start

Requirements:

- Python 3.11+
- Go 1.23.1 if using Go tools or the V2Ray collector
- Telegram credentials appropriate to the configured source/destination types

```bash
git clone https://github.com/AmirrezaFarnamTaheri/HUNTX.git
cd HUNTX
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

For a local configuration, copy the production example and provide required credentials through environment variables rather than embedding secret values in source control:

```bash
cp configs/config.prod.yaml my_config.yaml
python scripts/make_telethon_session.py
huntx --config my_config.yaml run
```

The production configuration expands `${TELEGRAM_API_ID}`, `${TELEGRAM_API_HASH}`, and `${TELEGRAM_USER_SESSION}` for MTProto sources. Publishing uses a destination-specific token when configured, otherwise `PUBLISH_BOT_TOKEN`, then `TELEGRAM_TOKEN`.

## CLI

Global options:

```text
--config PATH      configuration file (default: config.yaml)
--data-dir PATH    runtime data root (default: ./data)
--db-path PATH     SQLite state database (default: ./data/state/state.db)
```

The installed `huntx` command exposes five subcommands:

### `huntx run`

Runs the governed pipeline and, unless disabled, post-run GatherX delivery.

```bash
huntx --config my_config.yaml run \
  --msg-fresh-hours 2 \
  --file-fresh-hours 48 \
  --msg-subsequent-hours 0 \
  --file-subsequent-hours 0
```

Relevant flags:

- `--no-publish` — build/export without publishing route artifacts to configured Telegram destinations.
- `--no-auto-deliver` — skip GatherX delivery after the pipeline completes.

Runtime tuning includes `HUNTX_MAX_WORKERS` (CLI default 3), `HUNTX_RUN_TIMEOUT`, `HUNTX_ALLOW_PARTIAL_EXPORT`, and `HUNTX_SESSION_LOCK_DIR` for overriding the host/user-wide MTProto session-lock directory.

### `huntx bot`

Runs GatherX persistently:

```bash
huntx bot
```

The bot uses `PUBLISH_BOT_TOKEN` first, then `TELEGRAM_TOKEN`. `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` are also required by the Telethon client.

### `huntx prune`

Prunes old state and only deletes raw blobs that are no longer referenced:

```bash
huntx prune --days 30
```

Retention must be a positive integer. Zero and negative retention values are rejected before destructive SQL runs.

### `huntx clean`

Removes runtime data/cache/log state while preserving registered GatherX users through the canonical database schema.

### `huntx reset`

Performs a factory reset of runtime state and source offsets. Without `--yes`, the CLI requires the exact interactive confirmation `RESET`.

## Production runtime architecture

```text
GitHub Actions / local CLI / GatherX admin run
                    |
                    v
          shared governed run service
                    |
          config load + validation
                    |
       process lock + session lock(s)
                    |
        production runtime factory
                    |
   source trust / canonical MTProto peers
                    |
     SQLite rolling-window LIFO queue
                    |
             Telegram MTProto
                    |
      +-------------+-------------+
      |                           |
      v                           v
content-addressed raw store     SQLite observations
      |                           |
      +-------------+-------------+
                    v
            bounded transform
                    |
             normalized records
                    |
        governed route build query
                    |
      artifacts / outputs / archive
          |                    |
          v                    v
 ledgered Telegram         GatherX approved
   publication              DM delivery
```

Important boundaries:

- **Source trust**: only publication-eligible sources seed/participate in governed output.
- **Durable queue**: production MTProto work is windowed, leased, retryable, and checkpointed transactionally with page persistence.
- **Raw/blob ownership**: binary handlers preserve source-blob identity so later ZIP builds cannot lose the underlying bytes.
- **Publication**: changed output is recorded through publication intents and destination delivery states before success is committed.
- **Bot authorization**: GatherX is private-chat only. Registration is not authorization.

See `docs/USER_GUIDE.md` for operator behavior and `docs/DEVELOPMENT.md` for implementation guidance.

## Formats

The repository registers these build-capable handlers:

- Text/proxy: `npvt`, `npvtsub`, `conf_lines`
- Raw/archive/enriched: `ovpn`, `npv4`, `ehi`, `hc`, `hat`, `sip`, `nm`, `dark`, `tut`, `sks`, `tmt`, `opaque_bundle`

`slipnet` is registered for parsing but is intentionally parse-only; configuration validation rejects parse-only formats in publication routes.

The current `configs/config.prod.yaml` route publishes 12 formats:

```text
npvt, npvtsub, conf_lines, ovpn, npv4, ehi,
hc, hat, sip, nm, dark, opaque_bundle
```

For `npvt`/`npvtsub` build results, HUNTX may also emit:

- `*.decoded.json`
- `*.b64sub`
- `*.singbox.json`

The sing-box derivative is intentionally narrower than URI recognition. A proxy URI can be valid and preserved while remaining ineligible for native sing-box conversion when required semantics are unknown or incomplete.

## GatherX authorization model

GatherX works only in direct messages.

Available while pending:

```text
/start  /help  /formats  /protocols  /myinfo  /ping
```

Approved-user commands:

```text
/get  /latest  /count  /setformat  /mute  /unmute
```

Private administrator commands:

```text
/status  /admin  /pending  /approve <id>  /deny <id>
```

Administrator identity is based on immutable numeric Telegram user IDs in `HUNTX_ADMINS`. Artifact delivery also rechecks approved private-chat identity at the lower delivery layer.

## Runtime storage

`HUNTX_DATA_DIR` defaults to `data/`. Within it, the runtime uses:

```text
data/raw/          SHA-256 raw blob store
data/artifacts/    configured artifact-store root support
data/dist/         internal/distributable material
data/outputs/      current generated outputs
data/outputs_dev/  cumulative developer proxy output
data/archive/      changed output archive
data/rejects/      rejected forensic payloads
data/state/        locks and default SQLite location
data/logs/         runtime logs / structured summaries
```

The SQLite database defaults to `data/state/state.db` and can be overridden with `HUNTX_STATE_DB_PATH` or `--db-path`.

The former tracked `data_archive/` snapshot tree was generated historical ballast and is not part of the live runtime model.

## GitHub Actions production control plane

`.github/workflows/huntx.yml` runs every two hours and can be dispatched manually. Its major stages are:

1. validate Go/Python release planes;
2. restore and cryptographically verify the current immutable S3 generation when configured;
3. run HUNTX under a watchdog;
4. verify output and construct site data;
5. build and verify a recoverable checkpoint generation;
6. publish structured runtime diagnostics;
7. persist the immutable generation to S3 when configured;
8. deploy verified site data to GitHub Pages when packageable output exists.

A separate generated-output workflow consumes successful production artifacts, maintains a generated-only branch, and mirrors the intended generated files into `main/outputs` and `main/outputs_dev`.

The real-investigation gate verifies structured metrics such as sources checked, messages scanned/new, and cursor updates from production run summaries.

## Development and validation

Install the development dependencies declared by the project, or use the exact CI lock:

```bash
python -m pip install -e ".[dev]"
```

Repository gates mirror CI:

```bash
gofmt -l .
go test -race ./...
go vet ./...
go build ./cmd/huntx-tools
go build ./cmd/huntx-engine

python -m compileall -q -j 0 src tests scripts
python -m flake8 src/huntx tests scripts --count --statistics
python -m mypy src/huntx
python -m pytest -q -m "not perf" --strict-config --strict-markers
```

Runtime dependencies are hash-pinned in `requirements.txt`; CI tooling is exact-version pinned in `requirements-ci.txt`.

## Security and operational notes

- Never commit bot tokens, API hashes, Telethon session strings, AWS credentials, or decryption keys/passwords.
- Log redaction covers normal messages and rendered traceback text, but secret-bearing exceptions should still be avoided by design.
- Network probes resolve and validate public addresses before dialing; private/special-use targets are rejected.
- Proxy configurations aggregate public third-party endpoints. HUNTX does **not** make those endpoints trustworthy; consumers must apply their own threat model.
- Repository code cannot rotate credentials that may have been exposed historically. Provider-side revocation/rotation is an external operational action.

## License

MIT
