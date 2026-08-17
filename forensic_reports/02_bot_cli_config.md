# Subagent B — HUNTX Bot / CLI / Config Forensic Report

Scope: `src/huntx/bot/`, `src/huntx/cli/`, `src/huntx/config/`, `src/huntx/logging_conf.py`, `src/huntx/utils/`, `configs/config.prod.yaml`, plus direct dependencies (`core/locks.py`, `core/session_lease.py`, `core/run_health.py`, `core/runtime_resilience.py`, `store/paths.py`, `state/consumer_reconciliation.py`, `store/artifact_store.py:list_archive`, `pipeline/publish.py` unknown_outcome path). All citations `file:line`. Read-only investigation.

**Live-verification status:** ✅ = confirmed by reading exact source lines; 🔍 = derived/inferred; ⚠️ = stale-risk.

---


## 1. Bot command surface (GatherX)

### 1.1 Class composition
`InteractiveBot(HandlersMixin, DeliveryMixin, AdminMixin)` — `bot/interactive.py:43`. Constructor (`interactive.py:47-78`): token-isolation check, opens state DB (`paths.STATE_DB_PATH`), creates `ArtifactStore`, `StateRepo`, Telethon client with session file `data/bot.session` (`interactive.py:77-78`).

### 1.2 Registered handlers (`handlers.py:19-35`)
14 NewMessage patterns (case-insensitive regex) + 1 global `CallbackQuery`:

| # | Command | Handler | Rate limit (cooldown) | Auth gate | Notes |
|---|---|---|---|---|---|
| 1 | `/start` | `_on_start` handlers.py:55 | 3s | none — registers user | Welcome + 4 quick buttons; logs new users |
| 2 | `/help` | `_on_help` handlers.py:79 | 3s | none | Same welcome payload |
| 3 | `/get [fmt]` | `_on_get` handlers.py:89 | 5s | none (registers) | No arg → quick-pick buttons; arg → `_send_format_to_user` |
| 4 | `/latest [days]` | `_on_latest` handlers.py:118 | 15s | none | default 4, `min(days,7)` cap (handlers.py:125-126) |
| 5 | `/formats` | `_on_formats` handlers.py:138 | **none** | none | text+binary format list |
| 6 | `/setformat [fmt]` | `_on_setformat` handlers.py:162 | **none** | none | validates vs `_ALL_VALID_FORMATS` (handlers.py:182) |
| 7 | `/myinfo` | `_on_myinfo` handlers.py:196 | **none** | none | settings card w/ mute toggle button |
| 8 | `/status` | `_on_status` handlers.py:268 | **none** | none | users/sources/files/records |
| 9 | `/protocols` | `_on_protocols` handlers.py:224 | **none** | none | from `formats.npvt._PROXY_SCHEMES` |
| 10 | `/count` | `_on_count` handlers.py:237 | **none** | none | expensive JSON-extract GROUP BY (`interactive.py:332-369`) |
| 11 | `/ping` | `_on_ping` handlers.py:261 | **none** | none | latency edit |
| 12 | `/mute` | `_on_mute` handlers.py:202 | **none** | none | `muted=1` |
| 13 | `/unmute` | `_on_unmute` handlers.py:214 | **none** | none | `muted=0` |
| 14 | `/admin [run\|prune N]` | `_on_admin` admin.py:35 | none | `_is_admin` numeric-ID | dashboard / trigger run / prune |
| 15 | CallbackQuery | `_on_callback` interactive.py:206 | cost-based (below) | admin branch gated | all inline buttons |

Public command menu (`SetBotCommandsRequest` at `interactive.py:298-309`) registers exactly the README's **13 commands** (`constants.py:30-50`): start, help, get, latest, formats, protocols, count, setformat, myinfo, status, mute, unmute, ping. **`/admin` is deliberately omitted from the menu (hidden command).** Menu registration failure is only a warning (`interactive.py:308-309`).

### 1.3 Authorization model
- **Registration ≠ authorization.** `/start` (and most commands) call `_register_user` (`interactive.py:119-132`) → row in `bot_users` with `approved INTEGER NOT NULL DEFAULT 0` (`interactive.py:88`).
- **Approval gate applies ONLY to auto-delivery**: `_get_active_users` selects `WHERE approved = 1 AND muted = 0` (`interactive.py:134-139`).
- **On-demand commands (`/get`, `/latest`, `/formats`, …) are NOT approval-gated** — any DM that can message the bot can pull files. The gate is a delivery gate, not a command gate.
- **There is NO approval workflow in code.** No `/approve`, `/deny`, `/list` handler exists anywhere in `src/` (verified by grep). The only `UPDATE bot_users SET approved = 1` in the repo is `tests/test_bot_authorization.py:17`. README:113 says "Administrator approves the user in the bot-user database/admin workflow" — i.e., manual SQL against the state DB. The approval feature is **schema + gate present, workflow absent** (see §6/§7).
- Admin identity: `_is_admin` (`admin.py:16-33`) reads `HUNTX_ADMINS` (comma list), **matches numeric IDs only**; non-numeric entries are logged as insecure and ignored (`admin.py:25-31`). The `username` parameter is accepted but never used — spoof-proof by design.
- Admin exemption from throttling: `_check_rate_limit` returns True immediately for admins (`interactive.py:176`).

### 1.4 Throttle mechanics
- Per-user in-memory cooldown `OrderedDict` (`interactive.py:75`), bounded: `_COOLDOWN_MAX_ENTRIES = 4096`, `_COOLDOWN_TTL_SECONDS = 3600.0` (`interactive.py:44-45`); LRU eviction + TTL prune (`interactive.py:166-172`).
- Message cooldowns: start/help 3s, get 5s, latest 15s (handlers.py:57,80,91,120). Over-limit → "⚠️ Slow down…{wait}s" via `event.answer` (callbacks) or `event.respond` (messages) (`interactive.py:183-191`).
- Callback cost tiers `_callback_cooldown` (`interactive.py:198-204`): `get:` → 8.0s; `setfmt:`/`cmd:` → 3.0s; everything else 5.0s.
- Callback dispatch (`interactive.py:206-293`): `admin:*` handled first (gated by `_is_admin`, `event.get_sender()` fetched but username unused, `interactive.py:212-230`); then rate limit; then `get:<fmt>` (whitelist-checked vs `_ALL_VALID_FORMATS`, `interactive.py:237`), `setfmt:<fmt>` (`interactive.py:244-257`), `cmd:{formats,myinfo,mute,unmute,setformat}` (`interactive.py:259-285`). Non-UTF-8 payloads rejected explicitly (`interactive.py:288-290`); generic catch-all answers "The request failed. Please try again later." with no exception detail (`interactive.py:291-293`).

### 1.5 Mute/unmute state
- Column `bot_users.muted INTEGER DEFAULT 0` (`interactive.py:89`). `/mute`→1 (`handlers.py:202-212`), `/unmute`→0 (`handlers.py:214-222`); callback variants register the user first, then UPDATE (`interactive.py:267-273`). `_respond_myinfo` renders toggle button `cmd:mute`/`cmd:unmute` (`handlers.py:318-321`).

### 1.6 `/get` format resolution (`delivery.py:288-324`)
1. Reject fmt not in `_ALL_VALID_FORMATS` (15 SUPPORTED + `b64sub`, `decoded.json`, `singbox.json`; `constants.py:52-70`).
2. Scan `paths.OUTPUT_DIR` sorted; match via `_filename_matches_format` (`delivery.py:274-286`); send every match (0.3s pacing, `delivery.py:314`).
3. If zero sent → fallback to archive: `_send_latest_to_user(chat_id, fmt=fmt, days=4)` (`delivery.py:317`).
4. Still zero → "No files found for `{fmt}`" (`delivery.py:318-324`).

### 1.7 `/latest` windowing (`handlers.py:118-136`, `delivery.py:326-357`)
- `days = int(arg) if arg.isdigit() else 4`, capped `min(days,7)` (`handlers.py:125-126`).
- `ArtifactStore.list_archive(days)` filters archive dir by `st_mtime >= now - days*86400`, newest first (`store/artifact_store.py:127-136`). No lower bound: `/latest 0` → empty-window message.

### 1.8 Admin workflows (`admin.py`)
- `/admin` → dashboard (users/sources/seen/records) with buttons `admin:run`, `admin:prune:30`, `admin:prune:15`, `admin:stats` (`admin.py:63-89`). `/admin run` and `/admin prune [N]` text subcommands (`admin.py:48-59`).
- **Trigger run** `_trigger_background_run` (`admin.py:91-132`): single-flight guard via `self._pipeline_task` (`admin.py:93-102`, covered by `tests/test_bot_admin_hardening.py`); runs `_run_pipeline_blocking` in executor thread → `deliver_updates_active()` → success/failure message to admin chat. `_run_pipeline_blocking` (`admin.py:134-150`): loads config from `HUNTX_CONFIG` (default `"config.yaml"`), validates, takes `state/huntx.lock`, runs `Orchestrator.run(timeout=16200, no_publish=HUNTX_BOT_NO_PUBLISH)`.
- **Prune** `_perform_admin_prune` (`admin.py:152-198`): `repo.prune_old_data(days)` then raw-store prune of **orphaned hashes only** (`candidate_hashes - get_all_known_hashes()`, `admin.py:171-176` — fix from commit 5229d0b "preserve shared raw blobs during admin prune").
- **Alert path** `send_freshness_alert` (`delivery.py:24-48`): sends "⚠️ [LOW FRESHNESS WARNING]" if `proxy_count < min_threshold` (default 10) else "✅ [PIPELINE REPORT]" to `admin_chat_id`, via `_send_with_floodwait`. **No production caller exists** — only `tests/test_bot_alerts.py:21,40`. Dead-but-tested feature (commit b6643c5).

---

## 2. Delivery subsystem (`bot/delivery.py`)

### 2.1 Tables (`interactive.py:97-117`)
- `bot_delivery_checkpoint(user_id PK, attempted, sent, failed, last_error, updated_at)` — per-user run summary.
- `bot_delivery_items(user_id, artifact_hash, artifact_name, delivered_at, PK(user_id, artifact_hash), FK→bot_users ON DELETE CASCADE)` — **per-user × per-content ledger**.

### 2.2 Auto-deliver flow after pipeline
`hardened_main._cmd_run` → unless `--no-auto-deliver` → `legacy._deliver_updates()` (`hardened_main.py:175-183`; `main.py:377-411`): builds a *second* `InteractiveBot` with `PUBLISH_BOT_TOKEN or TELEGRAM_TOKEN`, manual event loop, `bot.deliver_updates()`, graceful task cancellation (`main.py:393-411`).
`deliver_updates` (`delivery.py:207-219`): `client.start(bot_token)` → `deliver_updates_active()` → disconnect in finally + 0.25s settle.
`deliver_updates_active` (`delivery.py:221-243`): users = approved+unmuted; files = `_collect_delivery_files(paths.OUTPUT_DIR)`; per user `_deliver_files_to_user`. In persistent-bot mode, `admin.run_pipeline_task` calls `deliver_updates_active()` directly on the already-connected client (`admin.py:109`).

### 2.3 File collection & archive-name matching (`delivery.py:245-286`)
- Default formats `_AUTO_DELIVER_FORMATS = ("npvt", "b64sub")` (`constants.py:72`) — **user `default_format` is NOT consulted for auto-delivery**; it only affects `/get`.
- Skips non-files and zero-byte files (`delivery.py:252`).
- `_filename_matches_format` (`delivery.py:274-286`): npvt/npvtsub → `.{fmt}` or `_{fmt}.txt`; b64sub family → `".b64sub" in name` or `_b64sub.txt`; decoded.json / singbox.json families similarly; generic fallback `.{fmt}` / `_{fmt}.txt|json|zip` — this fallback is the archive-artifact-name matching from commit 5792367.
- Captions specialized for `.npvt`, b64sub, decoded.json, singbox.json, and binary extensions `.ovpn .ehi .hc .hat .sip .nm .dark .npv4` (`delivery.py:259-270`).

### 2.4 Per-user/per-content checkpoints & resume (`delivery.py:50-96,149-205`)
- `_artifact_hash` = streaming SHA-256 of file bytes, 1 MiB chunks (`delivery.py:50-56`).
- `_pending_delivery_files` (`delivery.py:58-77`): candidates minus hashes already in `bot_delivery_items` for that user → **resume sends only uncheckpointed content**. Verified by `tests/test_delivery_resume.py` (retry sends only the failed file; changed content with same filename is redelivered because hash differs).
- `_record_delivered_item` (`delivery.py:79-96`): upsert on `(user_id, artifact_hash)` — recorded **immediately after each successful send** (`delivery.py:182`), so a crash mid-batch resumes at file granularity.
- `_deliver_files_to_user` (`delivery.py:149-205`): header message first (FloodWait-wrapped); per file try/except — failure increments `failed`, stores `last_error = type(exc).__name__` only (no message → no leak), continues to next file; 0.3s pacing; outer except counts remainder failed; `finally` always writes checkpoint (`delivery.py:197-204`). Checkpoint with `sent>0` also bumps `bot_users.last_delivered_at` (`delivery.py:143-147`). Empty pending set → zeroed checkpoint (`delivery.py:158-164`).

### 2.5 FloodWait handling (`delivery.py:98-116`)
Bounded retry: `HUNTX_FLOODWAIT_MAX_SECONDS` (default 60), `HUNTX_FLOODWAIT_MAX_RETRIES` (default 2). Re-raises when `delay <= 0`, `delay > max_wait`, or retries exhausted. Fallback `FloodWaitError` stub if Telethon missing (`delivery.py:9-14`). Env parsing is raw `int()` — not the fail-soft `utils/env.py` helpers (see §7).

### 2.6 unknown_outcome (publish ledger, out of bot scope but requested)
`pipeline/publish.py:171-178`: if prior delivery state is `unknown_outcome`, automatic resend is **refused** ("reconcile the remote receipt before retrying") and counted as failure; state machine `desired/sending/confirmed/failed/unknown_outcome/skipped` (`state/schema.sql:96`); `mark_delivery_failed(..., unknown_outcome=isinstance(exc, UnknownPublicationOutcome))` (`publish.py:211-218`; exception class `publishers/telegram/publisher.py:24`).

---

## 3. CLI

### 3.1 Entry points
- Console script `huntx = huntx.cli.hardened_main:main` (`pyproject.toml:31`).
- `python -m huntx` → `src/huntx/__main__.py` → same hardened main.
- Legacy `cli/main.py` is reachable directly (`python -m huntx.cli.main`, `__main__` guard at main.py:454-455) but **not** via the installed entry point. Hardened main *delegates* to legacy: `main()` monkeypatches `legacy._cmd_run = _cmd_run` then calls `legacy.main()` (`hardened_main.py:186-189`). So `run` is hardened; `bot`/`clean`/`reset`/`prune` are legacy implementations.

### 3.2 Global flags (`main.py:17-20`)
`--config` (default `config.yaml`), `--data-dir` (default `./data`), `--db-path` (default `./data/state/state.db`). Hardened main injects CLI > env > default precedence for `--data-dir`/`--db-path` before argparse: `HUNTX_DATA_DIR`, `HUNTX_STATE_DB_PATH` (`hardened_main.py:48-61`).

### 3.3 Subcommands (5, not the 4 the README claims)
| Sub | Impl | Flags | Behavior |
|---|---|---|---|
| `run` | hardened `_cmd_run` (hardened_main.py:80-183) | `--msg-fresh-hours` (2), `--file-fresh-hours` (48), `--msg-subsequent-hours` (0), `--file-subsequent-hours` (0), `--no-auto-deliver`, `--no-publish` (main.py:25-55) | OptimizedHardenedOrchestrator + GovernedBuildPipeline + consumer reconciliation + health gate + auto-deliver |
| `bot` | `_cmd_bot` main.py:166-193 | `--token`, `--api-id`, `--api-hash` | persistent InteractiveBot; token = arg > `PUBLISH_BOT_TOKEN` > `TELEGRAM_TOKEN`; F-09 shared-token warning (main.py:179-185) |
| `clean` | `_cmd_clean` main.py:251-294 | `--yes/-y` | deletes raw/outputs/dev_outputs/artifacts/rejects/logs + state DB; **backs up & restores `bot_users`** (main.py:280-292) |
| `reset` | `_cmd_reset` main.py:297-374 | `--yes/-y` (else type `RESET`) | factory reset incl. `STATE_DIR` (source offsets); DB backup to `.db.bak` (main.py:335-341); restores bot_users; rewrites output READMEs |
| `prune` | `_cmd_prune` main.py:414-451 | `--days` (30) | manual DB + raw-store prune — **undocumented in README** |

Hidden/undocumented: `prune` subcommand; global `--config/--data-dir/--db-path`; env knobs below; `interactive.py:372-383` `__main__` dev entry (`--token/--api-id/--api-hash` argparse, basicConfig INFO).

### 3.4 `run` internals (hardened)
- `apply_runtime_resilience()` at import (`hardened_main.py:22`) monkeypatches `OptimizedHardenedOrchestrator` with canonical-channel dedupe (`_canonical_ingestion_sources`, resolves `@username` peers to numeric channel IDs, terminalizes alias duplicates — this is how the 56 `@peer` + 29 numeric sources in prod config are deduped at runtime), bounded timeouts, LIFO window metrics (`core/runtime_resilience.py`).
- Workers: `HUNTX_MAX_WORKERS` default 3, `max(1, int())`, no upper bound (`hardened_main.py:81-86`).
- Timeout: `HUNTX_RUN_TIMEOUT` default **12600** (`hardened_main.py:100-105`); legacy default was **9000** (`main.py:130`); admin-triggered run hardcodes **16200** (`admin.py:150`); `commands/run.py:31` 12600.
- `HUNTX_ALLOW_PARTIAL_EXPORT` default True (`hardened_main.py:94`).
- **Locks**: process lock `state/huntx.lock` via `acquire_lock` (`core/locks.py:9-42`): non-blocking `fcntl.lockf`/`msvcrt.locking`, raises `RuntimeError("Another instance of HuntX is already running.")` on contention.
- **Session lease**: if `TELEGRAM_USER_SESSION` non-empty, also acquires `acquire_lock(session_lease_path(STATE_DIR, identity))` (`hardened_main.py:108-114`); `session_lease_path` = `state/session-leases/sha256(identity)[:24].lock` (`core/session_lease.py:28-30`). Note: the CLI uses the *file-lock* on the lease path, not the full async lease protocol (`acquire_session_lease`, `core/session_lease.py:169-220`, with O_EXCL create, `.reap` markers, heartbeat, stale reclamation after 4h) — that async machinery has **no production caller** (grep: only its definition).
- Consumer reconciliation: `reconcile_configured_bot_consumers` (`state/consumer_reconciliation.py:142-168`) — token fingerprints (SHA-256, never raw tokens in DB), non-authoritative mode when any token unresolved (no deactivation/purge).
- Health gate: `evaluate_run_health`/`emit_run_health` (`core/run_health.py`): fatal only for `_FATAL_REASONS` (invalid_configuration, no_approved_sources, security_violation, state_corruption, unrecoverable_state, invariant_violation), timeout/failed-without-recoverable-progress; everything else "degraded success". `_all_publish_failures_are_fatal` shim always False — publish failures never fatal (`hardened_main.py:64-77`). JSON envelope logged as `HUNTX_RUN_HEALTH=…` and optionally written to `HUNTX_RUN_SUMMARY_PATH` (`run_health.py:212-254`).
- Post-run delivery failure is swallowed + counted (`hardened_main.py:175-183`).

### 3.5 Exit codes
- Fatal health gate → `SystemExit(1)` (`hardened_main.py:143-150`); unhandled exception → run-health envelope + `SystemExit(1)` (`hardened_main.py:161-173`); lock contention → uncaught `RuntimeError` → traceback, exit 1. Success → 0. Legacy path uses `sys.exit(1)` (`main.py:142,145,153,156,159`).

### 3.6 `cli/commands/run.py` — orphaned alternate implementation
`run_command(config_path)` (`commands/run.py:15-70`): stricter env handling (`env_int` bounds 1..64; `HUNTX_RUN_TIMEOUT` raises ValueError if non-numeric/≤0), plain `Orchestrator`, health gate raises RuntimeError. **Not wired to any entry point** — no `__init__.py` in `commands/`, no importer in `src/`; only exercised by `tests/test_audit_remediation.py:90`. Dead code / retained audit artifact.

### 3.7 Signal handling
**None.** No `signal` module usage anywhere in `src/huntx/cli/` or `src/huntx/core/` (grep verified). Shutdown relies on Telethon disconnect paths and lock release in `finally`.

---

## 4. Config system

### 4.1 Load pipeline
`load_config` (`config/loader.py:10-29`): existence check (FileNotFoundError) → `yaml.safe_load` → `recursive_expand` (env) → `AppConfig.model_validate` (pydantic v2; errors logged + re-raised).

### 4.2 Env expansion (`config/env_expand.py`)
Pattern `\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}` (`env_expand.py:6`). `${VAR}` **required** — unset → `ValueError("Missing required environment variable: …")` (fail loud, `env_expand.py:35`); `${VAR:-default}` optional (empty default allowed). Recursive over dict/list/str (`env_expand.py:40-48`). Deliberate contrast documented in `utils/env.py:11-15`: YAML refs fail loud; runtime tuning knobs fail soft.

### 4.3 Schema tree (`config/schema.py`)
```
AppConfig (schema.py:153-159)
├── sources: List[SourceConfig]
│   └── SourceConfig (93-119)
│       ├── id: str                       (non-empty, no unexpanded ${ — validate.py:47)
│       ├── type: str                     validator: telegram|telegram_user|v2ray_collector (103-108)
│       ├── selector: SourceSelector{include_formats: List[str]} | None (89-90)
│       ├── telegram: TelegramSourceConfig | None (44-55)
│       │   ├── token: Optional[str]      validator: falsy or no ":" → None (48-55)
│       │   └── chat_id: str
│       ├── telegram_user: TelegramUserSourceConfig | None (58-86)
│       │   ├── api_id: Optional[int]     validator: ""/0/"0"→None; unparseable → loud ValueError (64-86)
│       │   ├── api_hash: Optional[str]
│       │   ├── session: Optional[str]
│       │   └── peer: str
│       ├── trust_state: SourceTrustState = APPROVED   (candidate|approved|degraded|quarantined|retired, 30-35)
│       ├── discovered_from: Optional[str]
│       ├── approval_evidence: List[str] = []
│       └── model_validator: discovered+approved requires approval_evidence (110-115)
│           property publication_eligible = trust_state==APPROVED (117-119)
└── publishing: PublishingConfig{routes: List[PublishRoute]} (149-150)
    └── PublishRoute (134-146)
        ├── name: str
        ├── from_sources: List[str]
        ├── formats: List[str]
        ├── destinations: List[DestinationConfig]
        │   └── DestinationConfig (122-131)
        │       ├── chat_id: str
        │       ├── mode: str = "telegram"  (normalizes post_on_change→telegram, 13-27)
        │       ├── caption_template: str = "{filename}"
        │       └── token: Optional[str]
        ├── publication_tier: PublicationTier = COMPATIBLE (raw|compatible|secure, 38-41)
        └── require_fresh_probe: Optional[bool]  (None → tier==SECURE, 142-146)
```

### 4.4 `validate_config` (`config/validate.py:13-129`)
- Registry format check incl. derived `*.b64sub/*.decoded.json/*.singbox.json` (`validate.py:95-112`).
- Unique source IDs; type/block cross-exclusion; unexpanded `${...}` rejected in id/chat_id/peer/api_hash/session/route name/destination chat_id (`validate.py:45-119`).
- **Strict mode** (`HUNTX_STRICT` or `CI` ∈ {1,true,TRUE}, `validate.py:39-43`): telegram token must resolve; telegram_user api_id/api_hash/session required; destination token must resolve via `destination.token > PUBLISH_BOT_TOKEN > TELEGRAM_TOKEN` (`validate.py:7-10,121-127`). Non-strict still rejects unexpanded `${` destination tokens (`validate.py:128-129`).

### 4.5 `configs/config.prod.yaml` (875 lines) — every key
- `sources:` — **85 entries** (matches WELCOME_TEXT "85 sources", constants.py:10): 29 numeric peers (`-100…`) + 56 `@username` peers. Each entry: `id` (`src_<peer>`), `type: telegram_user`, `selector.include_formats: [all]` (YAML anchor `&id001` defined at line 6, reused everywhere), `telegram_user.{api_id: ${TELEGRAM_API_ID}, api_hash: ${TELEGRAM_API_HASH}, session: ${TELEGRAM_USER_SESSION}, peer}`. No `trust_state`/`discovered_from` → all default **APPROVED** and publication-eligible. No `telegram` (bot-token) sources.
- `publishing.routes[0]`: `name: all_sources`; `from_sources:` all 85 IDs (lines 773-858); `formats:` 12 — npvt, npvtsub, conf_lines, ovpn, npv4, ehi, hc, hat, sip, nm, dark, opaque_bundle (859-871; no b64sub/decoded.json/singbox.json in the route — those are derived/bot-side); `destinations[0]`: `chat_id: "8526064109"`, `mode: post_on_change` (alias → telegram, hash-suppressed posting), `caption_template: "Merged configs – updated {timestamp}"` (872-875). **No destination `token`** → runtime falls back to `PUBLISH_BOT_TOKEN`/`TELEGRAM_TOKEN` (`validate.py:10`). No `publication_tier` → COMPATIBLE; `require_fresh_probe` unset → False.
- Env vars required to load prod config: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_USER_SESSION` (all bare `${}` → fail loud if unset).

### 4.6 Secrets handling & redaction (`logging_conf.py`)
- `_RedactSecretsFilter` (`logging_conf.py:8-36`) on console + file handlers: bot token in `api.telegram.org` URLs, generic `\d+:<30+ chars>` token pattern, and KV pairs for TELEGRAM_TOKEN, PUBLISH_BOT_TOKEN, AWS_SECRET_ACCESS_KEY, AWS_ACCESS_KEY_ID, TELEGRAM_API_HASH, TELEGRAM_USER_SESSION, AWS_SESSION_TOKEN. On redaction, `record.args = ()` prevents re-formatting leaks (`logging_conf.py:31-34`).
- RotatingFileHandler 10 MB × 5 backups (`logging_conf.py:69-71`); urllib3/telethon/asyncio pinned to WARNING (`logging_conf.py:83-85`).
- Consumer reconciliation stores only SHA-256 token fingerprints (`consumer_reconciliation.py:158`).

### 4.7 Utils
- `utils/atomic.py`: `atomic_write` (mkstemp+fsync+os.replace, preserves existing mode bits, dir-fsync on POSIX, `atomic.py:54-111`); `atomic_write_if_changed` byte-compares first (`atomic.py:114-120`).
- `utils/env.py`: `env_int`/`env_bool` fail-soft with bounds + warnings (`env.py:27-90`).
- `utils/content_type.py`: `is_executable` magic-byte scanner; recursive ZIP scan with depth≤3, ≤500 entries, 50 MB aggregate decompression budget tracked on *actual* bytes read, Zip-Slip name checks, APK detection (`content_type.py:19-166`).
- `utils/safe_names.py`: `safe_component` / `safe_zip_entry_name` basename-only sanitizers (`safe_names.py:7-48`).
- `utils/profiler.py`: `wall_clock`, `rss_mb` benchmark helpers (`profiler.py:12-29`).

---

## 5. Security posture

1. **Shared-token fail-closed**: `InteractiveBot.__init__` raises RuntimeError if `token == TELEGRAM_TOKEN` unless `HUNTX_ALLOW_SHARED_BOT_TOKEN ∈ {1,true,yes}` (`interactive.py:51-57`); explicit opt-in logs a 409-conflict warning (`interactive.py:58-61`). `_cmd_bot` additionally warns (F-09) without blocking (`main.py:179-185`) — the constructor is the actual gate.
2. **Error redaction to users**: callback catch-all is generic (`interactive.py:293`); delivery `last_error` stores exception *class name only* (`delivery.py:185,195`); log redaction filter (§4.6). **Exception: admin-facing messages embed raw `{exc}`** (`admin.py:119,196`) — admin-only, but leaks paths/stack text into Telegram.
3. **Input bounds**: format whitelists (`interactive.py:237,246`; `handlers.py:182`; `delivery.py:289`); `/latest` ≤7 days (`handlers.py:126`); cooldown map bounded (§1.4); UTF-8-strict callback decode (`interactive.py:208,288`); admin numeric-ID-only (`admin.py:23-33`); zip-bomb/zip-slip bounds (`content_type.py`); filename sanitizers (`safe_names.py`).
4. **Admin exemption**: admins bypass message/callback cooldowns (`interactive.py:176`) and the admin callback branch bypasses the cost throttle entirely (`interactive.py:212-230` runs before `_check_rate_limit`).
5. **Registration ≠ authorization** for delivery (§1.3); deny-by-default `approved=0`.
6. **No secrets in YAML** — all credentials via env; unexpanded `${}` is a validation error; strict mode resolves publish credentials with runtime precedence (`validate.py:121-127`).

---

## 6. Hidden / incomplete features

| Item | Evidence | Status |
|---|---|---|
| User approval workflow (`/approve`, `/deny`, `/list`) | no handler in `src/`; only `tests/test_bot_authorization.py:17` sets approved=1; README:113 defers to "database/admin workflow" | **Missing** — gate exists, admin UX does not |
| `send_freshness_alert` | `delivery.py:24-48`, callers only in `tests/test_bot_alerts.py` | Dead in prod (commit b6643c5) |
| `huntx prune` subcommand | `main.py:74-79,414-451` | Undocumented in README |
| `/admin` command | registered (`handlers.py:34`) but absent from command menu (`constants.py:30-50`) | Hidden by design |
| `cli/commands/run.py` | no importer; tests only | Orphaned |
| Async `acquire_session_lease` protocol | `core/session_lease.py:169-220`; no caller | Unused (CLI uses plain file lock on the lease path) |
| `HUNTX_BOT_NO_PUBLISH` | `admin.py:149` | Undocumented env knob |
| `HUNTX_RUN_SUMMARY_PATH` | `run_health.py:236` | Undocumented env knob |
| `interactive.py:372-383` `__main__` dev runner | argparse token/api-id/api-hash | Dev backdoor entry |
| Feature-flag envs (run path) | `HUNTX_ALLOW_PARTIAL_EXPORT` (hardened_main.py:94), `HUNTX_ALLOW_PARTIAL_SUCCESS` (legacy gate, main.py:139), `HUNTX_STRICT`/`CI` (validate.py:39), `HUNTX_MAX_WORKERS`, `HUNTX_RUN_TIMEOUT`, `HUNTX_FLOODWAIT_MAX_SECONDS/_RETRIES`, `HUNTX_ADMINS`, `HUNTX_ALLOW_SHARED_BOT_TOKEN`, `HUNTX_DATA_DIR`, `HUNTX_STATE_DB_PATH`, `HUNTX_CONFIG`, `LOG_LEVEL`, `TELEGRAM_USER_SESSION` (lease), `PUBLISH_BOT_TOKEN`, `TELEGRAM_TOKEN/API_ID/API_HASH` | Full env surface |
| No TODO/FIXME markers | grep across bot/cli/config/utils/logging_conf returned none | Clean |

---

## 7. Defects & risks (evidence-backed, live-verified where marked)

1. ✅ **No approval mechanism → delivery silently dead until manual SQL.** `approved` defaults 0 (`interactive.py:88`), nothing in `src/` ever sets it to 1 (grep confirmed: only `tests/test_bot_authorization.py:17` sets approved=1). Fresh deploy: `_get_active_users()` always returns empty → "No registered users — skipping delivery." (`delivery.py:223-224`). **Highest-impact gap vs README promise.**

   *Minimal fix plan (T9):* Add `/approve <user_id>`, `/deny <user_id>`, `/list pending` to `bot/admin.py`. Admin-gated, numeric IDs only. Persist `UPDATE bot_users SET approved=1 WHERE user_id=?`. Update `_get_active_users` query to return a meaningful count. Add test in `test_bot_authorization.py`.

2. ✅ **`clean`/`reset` subscriber restore is broken.** `_backup_bot_users` does `SELECT *` (`main.py:209`), which includes `approved` from the live schema (`interactive.py:88`). `_restore_bot_users` recreates the table **without** the `approved` column (`main.py:226-236` — the CREATE TABLE DDL has 7 columns: user_id, chat_id, username, registered_at, muted, last_delivered_at, default_format; `approved` is absent). The subsequent INSERT with backup's full column list raises `OperationalError: table bot_users has no column named approved`. This is caught and logged silently (`main.py:247-248`) — all subscribers are lost on every clean/reset.

   *Verified location:* `cli/main.py:226-236` — grep for "approved" in the CREATE TABLE block returns zero matches.

   *Minimal fix (T1) — add one line:*
   ```python
   # In _restore_bot_users, inside CREATE TABLE IF NOT EXISTS bot_users ():
   # After line 234 (default_format TEXT DEFAULT 'npvt'), add:
   approved INTEGER NOT NULL DEFAULT 0
   # Then add regression test: _backup_bot_users → _cmd_clean → _restore_bot_users → assert approved survives
   ```

3. ✅ **Admin-triggered pipeline uses default config path `config.yaml`** (`admin.py:142`) which does not exist in the repo (only `configs/config.prod.yaml`) → `/admin run` fails with FileNotFoundError unless `HUNTX_CONFIG` is exported as an environment variable before starting the bot.

   *Fix (T12):* `config_path = os.getenv("HUNTX_CONFIG", "configs/config.prod.yaml")` at `admin.py:142`.

4. ✅ **CLI `prune` lacks the orphan-hash guard** that admin prune has. `main.py:444-446`: `raw_pruned = raw_store.prune_by_hashes(raw_hashes)` where `raw_hashes` = all age-eligible raw hashes from `prune_old_data`. `admin.py:171-176` correctly subtracts `get_all_known_hashes()` first (commit 5229d0b "preserve shared raw blobs during admin prune"). The CLI path can delete raw blobs still referenced by live records in the DB.

   *Fix (T4) — 3 lines replacing main.py:446:*
   ```python
   live_hashes = set(repo.get_all_known_hashes())
   orphan_hashes = [h for h in raw_hashes if h not in live_hashes]
   raw_pruned = raw_store.prune_by_hashes(orphan_hashes)
   ```

5. ✅ **Unthrottled expensive endpoints**: `/count` (JSON-extract GROUP BY over all active records, `interactive.py:343-364`), `/status`, `/protocols`, `/formats`, `/ping`, `/setformat`, `/mute`, `/unmute`, `/myinfo` have **no rate limit** (only start/help/get/latest call `_check_rate_limit`). `/count` is a cheap DoS vector requiring only a registered account.

   *Fix (T13):* Add `_check_rate_limit(event, seconds=N)` at entry of each unthrottled handler. Recommended cooldowns: `/count` 30s, `/status` 10s, `/formats`/`/protocols` 5s, `/ping`/`/setformat`/`/mute`/`/unmute`/`/myinfo` 3–5s.

6. 🔍 **Unbounded send volume per request**: `/get <fmt>` sends *every* matching file in OUTPUT_DIR (`delivery.py:300-314`) and `/latest` sends every archive file in window (`delivery.py:337-349`) — no per-request file-count cap; only 0.3s pacing + FloodWait bounds. A user requesting a wide format match gets unlimited files.

   *Fix (T13):* Cap at `HUNTX_BOT_MAX_FILES_PER_REQUEST` (env int, default 10). Add `files_sent` counter; break on cap; append "Showing {cap} of {total} files. Use /latest for specific dates." message.

7. 🔍 **O(users × files × size) hashing**: `_pending_delivery_files` recomputes SHA-256 of all candidate files for every user (`delivery.py:63` called inside per-user loop `delivery.py:240`). Hashes are content-global; precomputing them once per delivery run would save ~N×M hash reads.

8. ✅ **`_register_user` upsert wipes stored username**: callers other than `_on_start` pass `username=None`. The UPDATE at `interactive.py:123-126` sets `username = ?` unconditionally → any later `/help`, `/get`, `/mute` etc. NULLs the username.

   *Fix (T15):* Change `interactive.py:124` to use `username = COALESCE(?, username)` in the UPDATE statement so non-None username updates propagate, but None callers preserve the existing value.

9. 🔍 **Raw `int()` env parsing in delivery** (`delivery.py:99-100`) raises uncaught ValueError on malformed `HUNTX_FLOODWAIT_MAX_*`, unlike the fail-soft `utils/env.py` policy; same for `int(os.environ.get("TELEGRAM_API_ID","0"))` in `_cmd_bot` (`main.py:172`) and `_deliver_updates` (`main.py:383`).

10. ⚠️ **Exception text leaked to admin chat**: `f"❌ **Pipeline execution failed:**\n`{exc}`"` (`admin.py:119`) and prune failure `{exc}` (`admin.py:196`). Admin-only path, but leaks file paths and stack fragments into Telegram messages.

11. 🔍 **Misleading stats**: `_get_user_count` computes `muted = total - active` (`interactive.py:147`), conflating *pending/unapproved* users with *muted* ones in `/status` and the admin dashboard.

12. ✅ **`_respond_myinfo` labels local time as UTC**: `datetime.datetime.fromtimestamp(...)` + "UTC" suffix (`handlers.py:308`). Should be `datetime.utcfromtimestamp(...)`.

13. 🔍 **Inconsistent defaults**: `HUNTX_RUN_TIMEOUT` 9000 (legacy, `main.py:130`) vs 12600 (`hardened_main.py:100`, `commands/run.py:31`) vs 16200 hardcoded (`admin.py:150`); `HUNTX_MAX_WORKERS` unbounded in hardened (`hardened_main.py:83`) vs bounded 1..64 in `commands/run.py:30`; two partial-success knobs (`HUNTX_ALLOW_PARTIAL_EXPORT` vs `HUNTX_ALLOW_PARTIAL_SUCCESS`).

14. 🔍 **`handlers.py:5` imports Telethon unconditionally**, defeating the try/except optional-import pattern in `interactive.py:8-18`/`constants.py:1-5` (moot in practice — telethon is a hard dependency, `pyproject.toml:12`, but it defeats the declared isolation contract).

15. ✅ **`/latest 0` accepted** (no lower bound, `handlers.py:125-126`) → guaranteed-empty window message with no useful feedback.

16. 🔍 **`_set_user_pref` is UPDATE-only** (`interactive.py:154-159`): `setfmt:` callback from a user who never `/start`ed silently no-ops (`interactive.py:249`) — then `/myinfo` prompts `/start`. Minor UX inconsistency.

17. 🔍 **`__pycache__` contains cpython-314 bytecode** alongside 311 (`src/huntx/bot/__pycache__/`) — indicates the tree was executed under a pre-release interpreter. Also `.pyc` files visible in git working tree.

18. ✅ **No signal handling** (§3.7): SIGTERM during a run leaves lock release to process-exit semantics only; Telethon tasks cancelled manually only in `_deliver_updates` (`main.py:399-410`). A `SIGTERM` during ingestion may leave the persistent queue's lease tokens stranded until `recover_expired_leases` on the next run.

---

## 8. Test coverage observed (scope-relevant)
`tests/test_bot_authorization.py` (deny-until-approved), `test_bot_admin_hardening.py` (single-flight run guard), `test_bot_alerts.py` (freshness alert), `test_delivery_resume.py` (per-content resume + changed-content redelivery), `test_bot_delivery_hardening.py`, `test_bot_handler_resolution.py`, `test_bot_interactive.py`, `test_bot_runtime*.py`, `test_config_loader.py`, `test_prod_config.py` (prod YAML loads+validates; asserts from_sources == sources count), `test_audit_remediation.py` (commands/run.py health gate).

**Coverage gaps:** No test for the H-1 clean/reset subscriber-restore bug. No test for the CLI `prune` orphan-hash gap. No test for the 8 unthrottled commands. The approval workflow has a test (`test_bot_authorization.py`) that manually writes the DB but no test of an actual `/approve` handler (because no handler exists). Adding a regression test for H-1 is a precondition of T1.

