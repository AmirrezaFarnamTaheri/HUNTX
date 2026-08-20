# HUNTX User Guide

This guide describes the current implemented operator and user behavior. Historical audit documents under `docs/history/` are retained as point-in-time records and may describe earlier runtime paths.

## 1. Configuration

HUNTX loads YAML and expands `${VAR}` environment references before Pydantic validation.

### Source types

#### MTProto user source

Production uses `telegram_user` sources for public-channel history and documents:

```yaml
sources:
  - id: public_channel
    type: telegram_user
    selector:
      include_formats: [all]
    telegram_user:
      api_id: ${TELEGRAM_API_ID}
      api_hash: ${TELEGRAM_API_HASH}
      session: ${TELEGRAM_USER_SESSION}
      peer: "@ChannelName"
```

The current `configs/config.prod.yaml` contains 85 `telegram_user` sources. During a governed run HUNTX canonicalizes Telegram channels, removes duplicate aliases from ingestion, seeds only publication-eligible sources, and processes closed time windows newest-first through the durable SQLite ingestion queue.

#### Telegram Bot API source

The `telegram` source type is implemented for bot-visible messages/updates:

```yaml
sources:
  - id: bot_channel
    type: telegram
    selector:
      include_formats: [all]
    telegram:
      token: ${TELEGRAM_TOKEN}
      chat_id: "-1001234567890"
```

Production does not currently use this source type. The connector persists fetched updates in the SQLite inbox before advancing Telegram offsets so a process crash cannot silently discard acknowledged updates.

#### V2Ray collector

`v2ray_collector` is also implemented. It executes the repository Go scraper package, consumes its generated config lines, and deduplicates them by full SHA-256 content identity. It is not part of the current production configuration.

### Source trust

Each source has a trust state. Publication is fail-closed: a source is eligible only when its effective trust state is approved. Discovered sources cannot be marked approved without approval evidence.

Revoking a source terminalizes unfinished durable ingestion work, including active leases. Window-page persistence and lease checkpointing share a transaction so a worker that loses its lease cannot partially commit the page after revocation.

### Publishing routes

Example:

```yaml
publishing:
  routes:
    - name: merged_vpn
      from_sources: [public_channel]
      formats: [npvt, npvtsub]
      publication_tier: compatible
      destinations:
        - chat_id: "-1009876543210"
          mode: post_on_change
          caption_template: "Merged configs — {timestamp}"
```

Configuration validation verifies:

- source and route IDs are unique;
- route names are canonical filesystem-safe names;
- all route source references exist;
- route formats are registered and build-capable;
- concrete output filenames do not collide;
- destination identities are unique;
- only implemented destination modes are accepted;
- required credentials are present in strict/CI mode.

Publication tiers are `raw`, `compatible`, and `secure`. Secure-tier build queries require matching record verdicts and can require a fresh successful probe. The current production route uses the compatible tier.

## 2. Formats

### Build-capable registered formats

| Format | Kind | Notes |
|---|---|---|
| `npvt` | text subscription | Validated proxy URI records |
| `npvtsub` | text subscription | Same canonical proxy-validation contract as `npvt` |
| `conf_lines` | text | Generic configuration lines |
| `ovpn` | raw/archive | OpenVPN source blobs |
| `npv4` | raw/archive + optional enrichment | NapsternetV v4 |
| `ehi` | raw/archive | HTTP Injector |
| `hc` | raw/archive | HTTP Custom |
| `hat` | raw/archive + optional enrichment | HA Tunnel / `happ://` metadata |
| `sip` | raw/archive | SocksIP Tunnel |
| `nm` | raw/archive + optional enrichment | NetMod |
| `dark` | raw/archive | Dark Tunnel |
| `tut` | raw/archive + optional enrichment | TUT |
| `sks` | raw/archive + optional enrichment | SKS |
| `tmt` | raw/archive + optional enrichment | TMT |
| `opaque_bundle` | raw/archive | Fallback for unrecognized binary data |

`slipnet` is registered for parsing but is parse-only. `validate_config()` therefore rejects it as a publication route format instead of allowing a route that cannot build an artifact.

The current production `all_sources` route configures these 12 formats:

```text
npvt, npvtsub, conf_lines, ovpn, npv4, ehi,
hc, hat, sip, nm, dark, opaque_bundle
```

### Raw-blob formats

Archive-style handlers preserve the source blob hash as part of the normalized record. This is required because their build step loads the original content-addressed bytes to create the final ZIP. Deep decryption/inspection is enrichment only; successful enrichment never replaces the canonical raw blob.

### Derived proxy outputs

Proxy routes can emit:

- `*.decoded.json` — structured decoded URI information;
- `*.b64sub` — base64 subscription text;
- `*.singbox.json` — only proxies whose semantics can be represented faithfully in the implemented sing-box mapping.

Recognition is intentionally broader than native sing-box conversion.

## 3. Proxy URI handling

`npvt` and `npvtsub` share one parser/validator. A recognized prefix alone is not enough: candidate URIs must pass protocol-aware validation before storage/build.

Recognized families include VMess, VLESS, Trojan, Shadowsocks, ShadowsocksR, Hysteria 1/2, Hysteria2 Realm, TUIC, SOCKS 4/4a/5, authenticated HTTP(S) proxies, SSH, ShadowTLS, NaiveProxy, Mieru, Juicity, AnyTLS, WireGuard-style links, WARP, DNS, and DNSTT.

Ordinary web URLs are not classified as proxy endpoints. Authenticated HTTP(S) proxy endpoints are accepted only when they match the endpoint shape expected by the validator.

## 4. Running locally

Install:

```bash
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e .
```

Create a Telethon session if using MTProto:

```bash
python scripts/make_telethon_session.py
```

Run:

```bash
huntx --config configs/config.prod.yaml run
```

Every supported run entrypoint reaches the same governed run service. That service performs config validation, acquires the runtime-state lock, acquires host/user-wide locks for every configured MTProto session identity, constructs the production orchestrator through `create_production_orchestrator()`, executes the bounded run, and emits structured health.

## 5. CLI reference

Global options:

| Option | Default | Meaning |
|---|---|---|
| `--config` | `config.yaml` | YAML configuration |
| `--data-dir` | `./data` | Runtime data root |
| `--db-path` | `./data/state/state.db` | SQLite database |

### `huntx run`

```bash
huntx --config my_config.yaml run [OPTIONS]
```

| Flag | Default | Meaning |
|---|---:|---|
| `--msg-fresh-hours` | `2` | First-seen text lookback |
| `--file-fresh-hours` | `48` | First-seen document lookback |
| `--msg-subsequent-hours` | `0` | Later text lookback (`0` = all unseen) |
| `--file-subsequent-hours` | `0` | Later document lookback (`0` = all unseen) |
| `--no-publish` | off | Skip route publication |
| `--no-auto-deliver` | off | Skip post-run GatherX delivery |

The local worker default is 3 through `HUNTX_MAX_WORKERS`. The production workflow explicitly supplies its own default of 2.

Runtime health uses three dispositions:

- `success` — no material degradation;
- `degraded` — useful/durable progress exists but one or more nonfatal stages degraded;
- `fatal` — configuration/state/invariant failure or execution failed without recoverable progress.

### `huntx bot`

```bash
huntx bot [--token TOKEN] [--api-id ID] [--api-hash HASH]
```

Token precedence is explicit `--token`, then `PUBLISH_BOT_TOKEN`, then `TELEGRAM_TOKEN`.

### `huntx prune`

```bash
huntx prune --days 30
```

Retention must be a positive integer. The repository layer rejects zero, negative, boolean, fractional, or string retention values before destructive SQL runs. Candidate raw blobs are deleted only after a post-prune live-reference check.

### `huntx clean`

Removes runtime data/cache/log material. Existing GatherX user rows are backed up and restored through the canonical current database schema.

### `huntx reset`

Factory-reset runtime state and source offsets. Without `--yes`, the local CLI requires typing `RESET` exactly. The GitHub Actions production reset is a different operational boundary and requires dispatch input `reset=true` plus exact `reset_confirm=RESET-HUNTX-STATE`.

## 6. GatherX bot

GatherX is **private-chat only**. Registration does not grant artifact access.

### Pending-safe commands

```text
/start  /help  /formats  /protocols  /myinfo  /ping
```

### Approved-user commands

```text
/get [format]
/latest
/count
/setformat <format>
/mute
/unmute
```

### Administrator-only commands

```text
/status
/admin
/pending
/approve <numeric_user_id>
/deny <numeric_user_id>
```

Administrator IDs come from `HUNTX_ADMINS` and only numeric immutable Telegram user IDs are honored. Administrative commands are not advertised in the default Telegram command menu.

Artifact delivery checks authorization again at the lower delivery boundary. Automatic delivery requires `user_id == chat_id`, `approved = 1`, and a non-muted user. Delivery item hashes and checkpoint counters are persisted so completed sends can be resumed without replaying every file.

## 7. Runtime state and storage

Default `HUNTX_DATA_DIR=data` layout:

```text
data/raw/          content-addressed raw source bytes
data/dist/         internal/distributable generated material
data/outputs/      current route outputs
data/outputs_dev/  cumulative developer proxy view
data/archive/      archive of changed output content
data/rejects/      rejected forensic payloads
data/state/        default SQLite/lock area
data/logs/         logs and structured run summaries
```

`HUNTX_STATE_DB_PATH` or `--db-path` controls the SQLite location.

The raw store shards SHA-256 filenames by prefix and verifies digest integrity on read. Generated output cleanup uses `.huntx-output-ownership.json`: only files explicitly owned by a previous manifest (or exact current outputs adopted during migration) are eligible for retention cleanup.

## 8. Production GitHub Actions

`.github/workflows/huntx.yml` runs every two hours and supports manual dispatch.

Major jobs:

1. **production-quality-gate** — Go format/race tests/vet/build plus pinned Python install, compile, Flake8, MyPy, and Pytest;
2. **restore-verified-state** — when S3 is configured, validate `current.json`, fetch the immutable generation manifest/payload, and verify it with `huntx-tools`;
3. **ingest-build-package** — run HUNTX under a watchdog, verify output, produce Pages data, build a verified checkpoint, and emit structured diagnostics;
4. **persist-immutable-state** — reverify the checkpoint, upload the generation, then advance the S3 pointer only after payload/manifest verification;
5. **deploy-pages** — deploy verified static site data when a packageable output exists.

Without an S3 bucket, the hosted runner is intentionally stateless across runs; the workflow still produces verified ephemeral checkpoints/artifacts for that run.

A separate `publish-generated-outputs.yml` workflow consumes a successful trusted production run, assembles a verified cumulative snapshot, updates the `generated-outputs` branch using concurrency-safe semantics, then mirrors the intended generated inventory into `main/outputs` and `main/outputs_dev`.

`huntx-real-investigation-gate.yml` verifies that a completed production run emitted a valid structured run summary with non-negative source/message/cursor metrics and rejects a run that had approved sources but checked none.

## 9. Secrets and decryption credentials

Do not store credential values in the repository. Relevant values include:

- `TELEGRAM_TOKEN`
- `PUBLISH_BOT_TOKEN`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_USER_SESSION`
- `HUNTX_ADMINS`
- AWS credentials/role configuration for optional persistence
- operator-supplied format decryption keys/passwords such as NetMod/TUT/HAPP/SlipNet credentials

Secret-dependent decryptors fail closed when required credentials are unavailable. Source blobs remain preservable/buildable even when optional deep-decryption enrichment cannot run.

## 10. Verification and troubleshooting

Local source gates:

```bash
python -m compileall -q -j 0 src tests scripts
python -m flake8 src/huntx tests scripts --count --statistics
python -m mypy src/huntx
python -m pytest -q -m "not perf" --strict-config --strict-markers
```

Go gates:

```bash
gofmt -l .
go test -race ./...
go vet ./...
go build ./cmd/huntx-tools
go build ./cmd/huntx-engine
```

Output verification used by production:

```bash
huntx-tools verify-output --data-dir persist/data
```

Site data generation used by production:

```bash
huntx-tools site-data --data-dir persist/data --docs-dir docs
```

If a run is degraded, inspect the structured `run-summary.json` and runtime logs rather than relying only on the process exit code. Logs redact known credential shapes in both ordinary messages and rendered exception traceback text.
