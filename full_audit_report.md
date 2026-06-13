<USER_REQUEST>
# HuntX / GatherX — Deep Technical Audit & Due-Diligence Report

**Audit scope:** Entire repository `AmirrezaFarnamTaheri/HUNTX` @ branch `main` (HEAD `6b13629`), all source, configuration, CI/CD, scripts, documentation, and committed artifacts.
**Audit method:** Full static code review of all 86 tracked source/config files (~19.6k LOC incl. tests, ~6.1k LOC core source), CI workflow analysis, data-flow tracing, adversarial threat modeling, and documentation/code drift comparison.
**Audience:** CTO, Principal Engineer, Security Auditor, Technical Due-Diligence Team.
**Date:** 2026-06-13

---

# 1. Executive Summary

HuntX is a zero-budget proxy-configuration aggregation pipeline. It scrapes VPN/proxy configs (vmess, vless, trojan, ss, hysteria2, tuic, wireguard, and ~15 more URI schemes) from **85 Telegram channels** via an MTProto user session, normalizes/deduplicates them through a 16-handler format registry into SQLite, builds merged artifacts, publishes them to Telegram destinations, auto-delivers them to subscribers of the **GatherX** interactive bot, and deploys a static catalog frontend to GitHub Pages — all orchestrated by a GitHub Actions cron job every 2 hours with optional S3 state persistence.

### Overall verdict (preview — full verdict in §18)

The codebase is **considerably more mature than typical hobby scrapers**: it has 29 test files, batch DB writes, WAL mode, atomic file writes, path-traversal guards, magic-byte executable filtering, flood-wait handling, reconnect/backoff logic, and structured logging throughout. However, it carries **systemic risks in four areas** that must be addressed before this could be considered production-grade or acquisition-safe:

1. **Output-path drift (P0, correctness):** The orchestrator exports artifacts to `persist/data/outputs/`, while CI commits the *repo-root* `outputs/` directory. The two never connect under the current CI invocation — the committed `outputs/` and `outputs_dev/` directories are **stale**, and the GitHub Pages "dev" catalog scans the stale repo-root `outputs_dev/`. The product's primary public deliverable is silently broken or serving outdated data.
2. **Shared MTProto session concurrency (P0, account survival):** One `TELEGRAM_USER_SESSION` string is shared across 85 sources and multiple worker threads, each constructing its own `TelegramClient` from the same `StringSession`. Concurrent use of one auth key from multiple connections is the canonical cause of `AUTH_KEY_DUPLICATED` — Telegram **revokes the session**, killing all 85 sources at once. The per-session `RLock` mitigation is acquired/released across method boundaries and is both fragile and throughput-destroying (it serializes all MTProto ingestion, negating the worker pool).
3. **Hard-coded third-party private keys (P1, legal/security hygiene):** `src/huntx/formats/common/crypto.py` embeds three reverse-engineered **RSA private keys** of HA Tunnel Plus, hard-coded AES passwords for HCTools (`.tut`/`.sks`/`.tmt`), the NetMod AES-ECB key, and a SlipNet XOR-assembled AES-GCM key. These trip every secret scanner, create IP/DMCA exposure, and ship decryption capability for other vendors' "protected" config formats.
4. **CI trust-boundary and timing flaws (P1, operations):** Unpinned dependencies (no lockfile, tag-pinned actions), `contents: write` pushes to `main` from cron, an orchestrator timeout (4.5 h) **longer** than the job timeout (3 h) so state is lost when the job is killed, a near-no-op lint gate (`flake8 --select=E9,F63,F7,F82`) contradicting README's "Quality Gates" claim, and a bot/pipeline `getUpdates` 409-conflict hazard when `PUBLISH_BOT_TOKEN` is absent.

There are also notable product/governance risks inherent to the domain: the system mass-redistributes **unverified proxy endpoints** to anonymous end users (MITM exposure for users, ToS exposure on Telegram and GitHub Pages), with no endpoint validation beyond optional TCP port checks in the (currently unused) Go collector.

**Bottom line:** strong engineering instincts, real test culture, and a coherent pipeline architecture — undermined by an unreconciled storage-layout refactor, a structurally dangerous Telegram session model, and embedded third-party key material. With ~2–4 focused engineering weeks the P0/P1 items are fixable; without them, the system will continue to run but its public outputs are unreliable and its single Telegram identity is one race condition away from revocation.

### Findings count by severity

| Severity | Count | IDs |
|---|---|---|
| Critical | 2 | F-01, F-02 |
| High | 7 | F-03, F-04, F-05, F-06, F-07, F-08, F-09 |
| Medium | 11 | F-10 … F-20 |
| Low | 8 | F-21 … F-28 |

---

# 2. System Overview

### 2.1 What the system does, end to end

1. **Ingest (Phase 1):** A thread pool (`HUNTX_MAX_WORKERS`, CI default 2) drains a queue of 85 configured sources. Each `telegram_user` source opens a Telethon client (shared session string), resolves a channel, and performs two passes — Pass 1 streams text messages in batches of 100; Pass 2 uses server-side `InputMessagesFilterDocument` to download files ≤25 MB, skipping APKs by name and executables by magic bytes. Items land in a content-addressed `RawStore` (SHA-256 sharded by 2-char prefix) and `seen_files` rows (status `pending`) in SQLite.
2. **Transform (Phase 2):** `get_pending_files` in batches of 200; per-file format detection (`core/router.decide_format` — extension first, then proxy-URI/base64 content heuristics), parse via registered `FormatHandler`, batch-insert `records` rows and batch-update statuses.
3. **Build (Phase 3):** Per route (one route, `all_sources`, in prod), SQL CTE dedup (`MAX(id)` per `(record_type, unique_hash)`), per-format `handler.build()`, plus derived artifacts for `npvt`/`npvtsub`: fully decoded JSON (`.decoded.json`) and base64 subscription (`.b64sub`). Artifacts saved to `data/dist/internal` (hash-named), `data/output` (latest, per route+format) and `data/archive` (timestamped, 4-day retention).
4. **Publish (Phase 3, parallel):** Per destination, change-detected via `published_artifacts` last-hash; hand-rolled multipart upload to Bot API `sendDocument`.
5. **Export (Phase 3b):** Writes route outputs to `paths.OUTPUT_DIR` (= `<data-dir>/outputs`) and an *all-time cumulative* dev set (`proxies.txt`/`.json`/`_b64sub.txt` + `_manifest.json`) to `<data-dir>/outputs_dev`.
6. **Cleanup (Phase 4):** Prunes processed raw blobs (keeping blobs still referenced by blob-dependent formats), prunes archive >4 days, prunes DB rows older than `HUNTX_PRUNE_DAYS` (30).
7. **Deliver:** `_deliver_updates()` spins up the GatherX Telethon bot, sends `npvt`/`b64sub` outputs to every non-muted registered user.
8. **CI wrap-up:** `verify_output.py` validates and packages `data/output` → `data/dist`; `generate_site_data.py` builds `docs/catalog.json` + copies artifacts into `docs/artifacts/`; commits `outputs/`, `outputs_dev/`, `docs/` to `main`; persists `state.db` + archive to S3; deploys `docs/` to GitHub Pages.

### 2.2 Runtime topology

- **Stateless compute:** GitHub Actions `ubuntu-latest` runner (cron `0 */2 * * *`, `concurrency: group huntx`, no cancel-in-progress).
- **State:** Single SQLite file (`persist/state.db` in CI), optionally round-tripped to S3 (`aws s3 cp`), plus the archive directory (`aws s3 sync`, upload-only).
- **Long-running mode:** `huntx bot` as a persistent process (a `scripts/systemd/mergebot.service` unit exists), sharing the *same* `state.db` and output directories with pipeline runs.
- **Frontend:** Static GitHub Pages site (`docs/`): Preact + Tailwind via CDN, Fuse.js search, no build step.

### 2.3 Scale parameters (evidence)

- 85 `telegram_user` sources (`grep -c "type: telegram_user" configs/config.prod.yaml` = 85); README claims "49+" (drift).
- 1 publish route (`all_sources`) fanning in all 85 sources.
- 16 registered format handlers (`formats/register_builtin.py` registers conf_lines, npvt, npvtsub, slipnet, ovpn, npv4, ehi, hc, hat, sip, nm, dark, tut, sks, tmt, opaque_bundle); README claims "12" (drift).
- ~19 proxy URI schemes recognized (`_PROXY_SCHEMES` duplicated in 4 modules — see F-15).

---

# 3. Architecture Analysis

### 3.1 Logical architecture — assessment

The layering is clean and conventional:

```
connectors/ (Bot API, MTProto, Go subprocess)
   → pipeline/ingest → store/raw_store + state/seen_files
   → pipeline/transform (core/router + formats/*)  → state/records
   → pipeline/build (formats/*.build + decoders)   → store/artifact_store
   → pipeline/publish (publishers/telegram)        → state/published_artifacts
   → orchestrator export                           → outputs / outputs_dev
   → bot/interactive (delivery + interactive UX)
```

**Strengths**
- Genuine pipeline separation: each phase is a class with a narrow interface; connectors implement a common `SourceConnector` protocol (`list_new(state) -> Iterator[SourceItem]`, `get_state()`).
- Content-addressed raw storage decouples ingestion from parsing and gives free dedup of identical payloads across sources.
- Incremental semantics are explicit: per-source `offset`, per-file `seen_files (source_id, external_id)` uniqueness, per-run `min_seen_file_id` delta for builds, per-destination publish change-detection.
- Format extensibility via `FormatRegistry` singleton + `register_builtin` is simple and adequately tested (`test_format_registry.py`, `test_formats_coverage.py`, `test_ported_formats.py`).

**Weaknesses**
- **Threading model fights the I/O model.** Ingestion uses OS threads, but Telethon is asyncio-based; each worker creates a fresh event loop per source (`orchestrator._ingest_one_source` lines 293–296) and uses `telethon.sync`. This works but multiplies connections per session (see F-02) and makes lifecycle cleanup error-prone (the `__del__`/`cleanup()` dance in the user connector, the manual loop teardown in `cli/main._deliver_updates`).
- **Global mutable path state.** `store/paths.py` uses module-level globals mutated by `set_paths()`, with the explicit caveat in `RawStore`/`ArtifactStore` ("compute default at runtime"). Any module that captures a path at import time silently binds the *old* location. This exact hazard materialized as F-01.
- **Singleton registry + class-level shared state** (`FormatRegistry.get_instance()`, `TelegramConnector._shared_state`, `TelegramUserConnector._session_locks`) make the system hostile to in-process parallel runs and complicate tests (which the team has worked around with thread-local injection hooks).
- **Five distinct "output" locations** exist: `data/output` (ArtifactStore latest), `data/dist` (verify/packaging), `data/outputs` (orchestrator export), `data/outputs_dev` (cumulative), repo-root `outputs//outputs_dev/` (CI-committed). No single source of truth; three scripts each pick a different one (F-01).

### 3.2 Deployment architecture — assessment

- Single GitHub Actions workflow does validation, run, packaging, repo commits, S3 persistence, and Pages deployment in one 180-minute job. There is no separation between the *build* identity and the *publish* identity — the cron job can write to `main` (F-07).
- The `concurrency: group: huntx` guard prevents overlapping CI runs, and a local `fcntl`/`msvcrt` file lock (`core/locks.py`) prevents overlapping local runs — but **nothing prevents the persistent `huntx bot` admin-triggered run (`/admin run`) from overlapping a CI run**, because they execute on different machines with different lock files but the **same Telegram session and same S3-restored state lineage** (F-02, F-10).

---

# 4. Component Inventory

| # | Component | Path | LOC | Purpose | Criticality | Maturity | Key risks |
|---|---|---|---|---|---|---|---|
| 1 | Orchestrator | `core/orchestrator.py` | 645 | Phase sequencing, worker pool, exports, cleanup | Critical | Medium | Timeout semantics (F-06), abandoned daemon threads (F-12) |
| 2 | Router | `core/router.py` | 73 | Filename/content format detection | High | High | Base64 sniff false positives (low) |
| 3 | Locks | `core/locks.py` | 41 | Cross-platform single-instance lock | Medium | Medium | `sys.exit(0)` on contention (F-19); unlock attempted even when never locked |
| 4 | Ingest pipeline | `pipeline/ingest.py` | ~190 | Batch dedup + raw save + state update | Critical | Medium | Hours-long single DB transaction (F-03); orphan blobs (F-13) |
| 5 | Transform pipeline | `pipeline/transform.py` | ~215 | Parallel parse, batch insert | High | High | Thread pool shares SQLite via per-call connections — OK |
| 6 | Build pipeline | `pipeline/build.py` | ~390 | Merge/dedup, decode vmess/ss/ssr, b64 sub | High | High | Derived artifact hash suffixing (F-17) |
| 7 | Publish pipeline | `pipeline/publish.py` | 148 | Change detection + multi-destination send | High | Medium | Strict-mode env coupling; partial-failure semantics OK |
| 8 | Bot API connector | `connectors/telegram/connector.py` | 338 | getUpdates polling, file download | Medium | Medium | 409 conflict with bot (F-09); unbounded shared cache (F-16) |
| 9 | MTProto connector | `connectors/telegram_user/connector.py` | 533 | History scan, 2-pass fetch, reconnect | Critical | Medium | Session sharing (F-02); cross-method lock (F-02) |
| 10 | Go collector connector | `connectors/v2ray_collector/` | 97 py + 649 go | Subprocess wrapper around `t.me/s/` HTML scraper | Low (unused in prod config) | Low | Requires Go toolchain absent from CI (F-20); generated files committed in source tree (F-22) |
| 11 | Format handlers | `formats/*.py` (16) | ~1.5k | Parse/build per format | High | High | Hard-coded vendor keys (F-04); ECB/PKCS1v15 (decrypt-only) |
| 12 | State repo | `state/repo.py` | 389 | All SQL access | Critical | High | Swallow-and-return-default error style hides corruption (F-18) |
| 13 | DB layer | `state/db.py` + `schema.sql` | 118 | Connection mgmt, schema, ad-hoc migration | Critical | Medium | No schema_version; single ALTER check (F-21) |
| 14 | Raw store | `store/raw_store.py` | 113 | CAS blob store | High | High | Orphan accumulation (F-13) |
| 15 | Artifact store | `store/artifact_store.py` | 157 | dist/internal, output, archive + traversal guards | High | High | — |
| 16 | Paths | `store/paths.py` | 60 | Mutable global path config | Critical | Low | Root cause of F-01 |
| 17 | Interactive bot | `bot/interactive.py` | 1067 | GatherX UX, delivery, admin panel | High | Medium | Username-based admin auth (F-05); no rate limiting (F-08); SQL string interpolation in `_get_protocol_counts` (F-14) |
| 18 | Telegram publisher | `publishers/telegram/publisher.py` | 95 | Hand-rolled multipart sendDocument | High | Medium | No retry on 429 despite parsing `retry_after` (F-24) |
| 19 | CLI | `cli/main.py` + `commands/run.py` | 387 | run/bot/clean/reset/prune | High | High | reset wipes `bot_users` (F-11) |
| 20 | Config | `config/{schema,loader,validate,env_expand}.py` | 230 | Pydantic models + `${VAR}` expansion | High | Medium | Missing env → `""` → opaque crash (F-23) |
| 21 | CI workflow | `.github/workflows/huntx.yml` | 295 | Everything | Critical | Medium | F-06, F-07, F-25, F-26 |
| 22 | Verify script | `scripts/verify_output.py` | 285 | Validate + package + optional v2ray exec | Medium | Medium | Executes native binary on untrusted config (F-27) |
| 23 | Site data script | `scripts/generate_site_data.py` | 132 | catalog.json + docs/artifacts | Medium | Low | Scans stale repo-root `outputs_dev` (F-01) |
| 24 | Frontend | `docs/index.html` + `docs/assets/js/*` | ~610 | Catalog UI (Preact/CDN) | Medium | Medium | All deps from CDN, no SRI (F-28) |
| 25 | Session script | `scripts/make_telethon_session.py` | 30 | Generate StringSession | Medium | Medium | Prints session to stdout (acceptable for purpose) |
| 26 | systemd unit | `scripts/systemd/mergebot.service` | — | Persistent bot | Low | Low | Not reviewed against current CLI flags |

**Secrets/credentials inventory:** `TELEGRAM_TOKEN`, `PUBLISH_BOT_TOKEN`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_USER_SESSION` (highest-value secret — full user-account access), `AWS_ACCESS_KEY_ID`/`SECRET` or `AWS_ROLE_ARN` (OIDC path exists), `S3_BUCKET`, `HUNTX_ADMINS`. Plus the **embedded third-party keys** in `crypto.py` (F-04). No secrets are committed for HuntX itself (verified by pattern scan).

---

# 5. Workflow Analysis

### 5.1 The 2-hour CI run — step-by-step with failure analysis

| Step | What happens | Failure modes observed in code |
|---|---|---|
| validate job | flake8 (E9/F63/F7/F82 only), mypy (`ignore_missing_imports`), pytest | Gate is far weaker than README claims (F-26) |
| Restore state | `aws s3 cp` state.db (`|| echo` tolerated), `aws s3 sync` archive (not tolerated — comment says abort to avoid wiping S3; **but the persist step uses upload-only sync, so the stated wipe risk doesn't exist**; meanwhile a transient sync failure *fails the whole run*) | Inverted risk tradeoff |
| Factory reset (opt-in) | `rm -rf` + S3 wipe (state.db backed up; **archive deleted with no backup**) | F-11: also destroys `bot_users` (all subscribers) |
| `huntx run` | Orchestrator with `timeout=16200` (4.5 h) inside a 180-min job | F-06: job is SIGKILLed at 3 h → **Persist state never runs** → entire run's offsets/files lost; next run refetches |
| verify_output | Validates `persist/data/output`, copies to `dist`, optionally executes `v2ray test` on aggregated untrusted outbounds | F-27 |
| generate_site_data (runs **twice**: once before artifact upload, once after persist) | Scans `persist/data/output` (latest), repo-root `outputs_dev` (stale — F-01), `persist/data/archive` | Duplicate step burns minutes; copies archive into `docs/artifacts/archive/` |
| Commit outputs | `git add outputs/ outputs_dev/ docs/catalog.json docs/artifacts/` then push with 5× retry + `git pull --rebase || true` | F-01: `outputs/`, `outputs_dev/` at repo root are never written by the pipeline (it writes `persist/data/outputs*`); only `docs/` actually changes. Rebase-retry can silently merge unrelated human commits into the bot push path |
| Persist state | `aws s3 cp` db + upload-only sync archive | Skipped entirely if any earlier step hard-fails or the job times out |
| Pages deploy | `docs/` | Public redistribution surface (see §7.6) |

### 5.2 GatherX user journey

`/start` → upsert into `bot_users` (same `state.db`) → welcome + inline buttons. `/get [fmt]` → whitelist check against `_ALL_VALID_FORMATS` → scan `paths.OUTPUT_DIR` with dual-naming matcher → fallback to 4-day archive. After each pipeline run, `_deliver_updates()` sends `npvt` + `b64sub` files to every active user with 0.3 s spacing. Mute/unmute, per-user default format, `/count` protocol histogram computed via SQLite `json_extract`. `/admin` (env-allowlisted) exposes **pipeline trigger** and **DB prune** to chat.

**Workflow-level issues:** delivery loop is strictly sequential per user with no flood-wait handling at this layer (Telethon will sleep internally, stretching delivery time linearly with user count — at 0.3 s × files × users, 1,000 users × 3 files ≈ 15+ min best case, hours with flood waits); failures are logged but never retried; no delivery queue or checkpoint (a crash mid-delivery re-sends to everyone or no one on next run depending on `last_delivered_at`, which is only updated per-user on success — acceptable).

---

# 6. Dependency Analysis

### 6.1 Direct runtime dependencies (`pyproject.toml`)

| Dependency | Constraint | Risk notes |
|---|---|---|
| telethon | `>=1.42,<2` | Core; well-maintained; the pin comment about `rsa`/`pyaes` insecure sdists shows supply-chain awareness |
| pydantic | `>=2.0` | Major-version floating (2.x breaking changes between minors have occurred) |
| PyYAML | `>=6.0` | `yaml.safe_load` confirmed in loader (no unsafe load found in scan) |
| cryptography | `>=41` | Only for ported decryptors |
| pyaes / rsa / pyasn1 | pinned floors | Telethon transitive hardening — good |

**No lockfile exists.** Every CI run resolves fresh latest-matching versions (F-25). Stdlib-only HTTP (`urllib`) avoids `requests` — fewer deps, but also no connection pooling, no system-level retry middleware, manual multipart (correctly implemented, boundary randomized via `secrets.token_hex`).

### 6.2 Hidden/implicit dependencies

- **Go toolchain** at runtime for `v2ray_collector` (`subprocess.run(["go", "run", "main.go"])`) — not installed in CI; the connector is configured in `schema.py` as a valid type but absent from prod config. Dead-but-armed integration (F-20).
- **`v2ray`/`xray` binary** optionally executed by `verify_output.py` (F-27).
- **CDN dependencies** in the frontend: Tailwind CDN script, esm.sh Preact/htm, Fuse.js, Lucide — no SRI hashes, no vendoring (F-28).
- **Cross-module duplication:** `_PROXY_SCHEMES` defined independently in `core/router.py`, `pipeline/build.py`, `formats/npvt.py`, `scripts/verify_output.py`; bot imports the *formats* copy. Adding a scheme requires 4 synchronized edits (F-15).

### 6.3 Circular/awkward dependencies

- `bot/interactive.py` imports the orchestrator lazily inside `_run_pipeline_blocking` (avoids a cycle, but means the bot process embeds the *entire pipeline* including its global path state — bot uses default `./data` paths unless env-configured, so a bot-triggered run can target **different directories** than CI runs; F-10).
- `ingest.py` contains a mid-function `import json` with an inline confession comment about serialization responsibility ("But wait, record_files_batch expects tuples…") — leftover reasoning-in-comments indicating unfinished refactor.

---

# 7. Security Assessment

### 7.1 Threat model

Actors: (a) malicious Telegram channel operators (supply chain of *content*), (b) anonymous bot users, (c) compromised PyPI/CDN packages, (d) GitHub actors with PR access, (e) Telegram/GitHub platform enforcement, (f) consumers of published configs.

### 7.2 Content supply chain (channel → user) — the core risk

The system ingests arbitrary bytes from 85 untrusted channels and **redistributes them** to bot subscribers and a public website. Defenses present: APK filename/extension skip, magic-byte detection of PE/ELF/Mach-O/APK (`utils/content_type.py`), 25 MB size cap, media-type drops. Defenses absent: no validation that proxy endpoints are benign (a hostile vmess server can observe/MITM all user traffic), no allowlist/denylist of destination hosts, no malware scan of ZIP *contents* (the code itself notes "Many malware samples are sent as ZIPs with .exe inside. For now, we'll label it as ZIP and let the connector decide" — and the connector passes ZIPs through into `opaque_bundle` artifacts that are then **published to users**). An attacker who controls any one of 85 channels can place arbitrary non-executable payloads (or executable payloads inside ZIPs) into the distributed bundles. **Severity: High (F-08a folded into F-08).**

### 7.3 Embedded key material (F-04)

`formats/common/crypto.py` ships: 3 RSA private keys (1024/4096/4096-bit, PKCS#1) for `happ://crypt{,2,3}` links; PBKDF2 passwords `fubvx788b46v`, `dyv35224nossas!!`, `fubvx788B4mev`; AES-ECB key `_netsyna_netmod_`; XXTEA with custom delta; a hex-XOR-assembled AES-256-GCM key "from Slipnet decoder.html". These are reverse-engineered from third-party apps (comments cite "vpndecrypt-Lol", "Pantegnos-main"). Consequences: GitHub secret scanning / GitGuardian alerts on every clone; potential DMCA/anti-circumvention exposure (DMCA §1201-adjacent in some jurisdictions); reputational risk in due diligence. They are *decryption* keys for content the system already receives, so the direct security blast radius is low — the exposure is legal/compliance, not confidentiality.

### 7.4 Bot attack surface

- **Admin auth (F-05):** `_is_admin` matches `HUNTX_ADMINS` against user_id **or username** (case-insensitive). Telegram usernames are transferable: if an admin releases their @handle, anyone who registers it gains `/admin` (pipeline trigger + DB prune). Numeric-ID-only matching is the safe form.
- **No rate limiting (F-08):** any user can loop `/latest 30` and force the bot to upload the entire 30-day archive repeatedly; combined with auto-registration this enables resource exhaustion and Telegram flood-bans of the bot identity.
- **SQL construction (F-14):** `_get_protocol_counts` builds `CASE WHEN … LIKE '{scheme.lower()}%'` via f-string interpolation. Inputs are the hard-coded scheme constants today, so it is **not currently injectable**, but it is a loaded pattern one refactor away from injection; everywhere else the codebase correctly uses parameterized queries.
- **Markdown injection (low):** filenames/captions are interpolated into `parse_mode="md"` messages with backticks; `safe_component` constrains charset, mitigating this.

### 7.5 CI/CD security

- `permissions: contents: write, pages: write, id-token: write` on a cron workflow whose push step does `git pull --rebase || true` then force-of-will pushes to `main`. A compromised dependency (unpinned pip install at run time — F-25) executes with repo-write and Pages-publish credentials, plus all Telegram and AWS secrets in env. Mitigations available: pin deps with hashes, pin actions to SHAs, split publish into a least-privilege job, push outputs to a dedicated branch.
- Static AWS keys path exists alongside the OIDC path; OIDC is correctly conditional but both can be configured simultaneously (the run uses static keys in `Restore state` regardless of OIDC step — note the `Restore state` step sets `AWS_ACCESS_KEY_ID` even when OIDC was configured, which **overrides** the OIDC credentials if both exist).
- `TELEGRAM_USER_SESSION` in GitHub secrets = full user-account takeover if exfiltrated (read DMs, join/leave, send as user). This is the crown-jewel secret and it is exposed to every step of a job that installs unpinned code (F-25 amplifies F-02's account risk).

### 7.6 Platform/abuse exposure

Scraping via MTProto user session at this scale risks Telegram limits/bans independent of bugs. Re-publishing channel content and hosting proxy lists on GitHub Pages may violate GitHub Acceptable Use depending on interpretation (proxy-list distribution is a gray zone; the Iran-focused channel set suggests censorship-circumvention purpose, which cuts both ways in policy reviews). This is a **business continuity** risk: both the compute platform and the distribution platform are free tiers of providers that can terminate unilaterally.

---

# 8. Reliability Assessment

### 8.1 Failure-mode catalog (verified in code)

| Failure | Handling | Gap |
|---|---|---|
| Telegram FloodWait | Sleep `e.seconds`, resume, no retry-count penalty (both passes) | Unbounded total stall; orchestrator timeout is the only backstop |
| Connection drop mid-iteration | 10 retries, stepped 2→32 s backoff, resume from `resume_after_id` | Good. But `ConnectionError` only; Telethon raises other transport errors (`RPCError` subclasses) that escape to the worker's catch-all and fail the source |
| Worker crash | Logged via `logger.exception`, source marked failed, run continues | Good isolation |
| Phase timeout | Phases 1–2 abort on deadline; Phase 3 deliberately runs anyway | **Daemon ingestion threads are abandoned, not stopped** (F-12): they keep downloading and writing to SQLite while build/cleanup runs; cleanup may prune blobs a zombie thread just wrote, or `seen_files` rows commit after export, corrupting next-run delta logic |
| DB write failure | Batch methods re-raise (transform aborts); ingest re-raises | Correct |
| Publish failure | Per-destination collected; any failure raises → artifact NOT marked published → retried next run | Correct at-least-once semantics |
| Empty/min ZIP artifacts | Skipped below 22-byte threshold | Fine |
| Crash mid-ingest | **Single connection held for the entire source run** (`ingest.run` wraps everything in one `with db.connect()`); commit happens only at context exit → a crash loses *all* seen_files rows and the offset for that source, while raw blobs are already on disk | F-03 (long write txn starves other workers under SQLite's single-writer model despite WAL; 30 s busy timeout is the only relief) + F-13 (orphan blobs are invisible to both prune paths, which iterate DB-known hashes only → unbounded disk growth across crashes) |
| Manifest corruption (`outputs_dev/_manifest.json`) | "starting fresh" on JSON error | Silent loss of all-time dedup history; manifest written **non-atomically** (`write_text`) unlike everything else (the project has `atomic_write` and doesn't use it here) — F-13b |
| Lock contention | `sys.exit(0)` | CI/systemd see **success** when a run was skipped (F-19); masks stuck-process incidents |

### 8.2 Idempotency & exactly-once analysis

- Ingest: idempotent via `(source_id, external_id)` UNIQUE + `INSERT OR IGNORE` + offset monotonicity. Re-runs after crash refetch but dedup. Correct.
- Transform: idempotent per file via status transitions; `records` has **no UNIQUE constraint on `(record_type, unique_hash)`** — duplicates accumulate and are resolved at read time by the `MAX(id)` CTE. Works, but table growth is unbounded between prunes and `idx_records_unique` is consulted constantly for an avoidable problem.
- Publish: at-least-once with change suppression — duplicate posts possible if `mark_published` fails after successful send (acceptable).
- Derived artifacts (F-17): hashes are `base_hash + "_dec"` / `"_b64"`. If decode/re-encode *logic* changes while base bytes don't, consumers get stale derived artifacts with no republish. Also `published_artifacts` change detection keys on `unique_id` = route:fmt, so this is consistent but logic-blind.

### 8.3 Recovery

S3 state restore makes the runner replaceable; archive is upload-only sync (good — no remote deletes). However: state.db is copied with **no integrity check** (a corrupted upload poisons all future runs; no `.bak` rotation except during factory reset), and WAL sidecar files (`state.db-wal/-shm`) are not synced — harmless because each run opens fresh, but a job killed mid-write uploads… nothing, because persist never runs (F-06). Net: state loss is the *common* failure mode under the current timeout configuration.

---

# 9. Scalability Assessment

| Axis | Current limit | Evidence | Breaking point |
|---|---|---|---|
| Source count | ~85, effectively **serial** for MTProto | per-session RLock serializes client creation/lifetime across threads (F-02) | More sources linearly extend run time; 2 h cron + 3 h cap collide |
| Worker parallelism | Nominal 2–3; real MTProto parallelism ≈ 1 | same | Raising `HUNTX_MAX_WORKERS` mostly burns threads |
| SQLite | Single-writer; WAL helps reads | `db.py`, ingest's long transactions | Concurrent bot + pipeline + zombie threads → busy timeouts at moderate scale |
| `records` table | Grows with duplicates until 30-day prune | no unique constraint | The build CTE (`filtered`/`dedup` over a JOIN) is O(rows) per route per run — fine at 10⁵, painful at 10⁷ |
| Dev manifest | All-time cumulative dict in RAM, JSON on disk, **also pretty-printed `proxies.json` with indent=2** | `_export_dev_outputs` | At ~10⁶ URIs: hundreds of MB JSON, multi-GB over repo history if it ever gets committed again; memory spikes each run |
| Bot delivery | Sequential, 0.3 s/file/user | `deliver_updates` | ~1k users is the practical ceiling before the delivery phase exceeds the cron interval |
| GitHub Pages artifacts | `docs/artifacts/` re-committed every run incl. archive copies | `generate_site_data.py` + CI commit | Repo size grows monotonically; GitHub soft limits (~1 GB warn, 5 GB hard pushback) will be reached; history is already polluted by "Update outputs [skip ci]" commits |
| Bot API getUpdates cache | Class-level dict, never evicted within process | `_shared_state` (F-16) | Long-lived processes leak; CI processes are short-lived (mitigates) |

---

# 10. Operational Assessment

**Observability:** Logging is genuinely excellent — phase banners, per-pass stats dicts, rates, durations, skip-reason counters, token masking. Logs are uploaded as CI artifacts (4-day retention). However there is **no alerting**: the orchestrator deliberately exits 0 on partial failure ("CI doesn't mark the whole job as failed"), so a run where *all 85 sources fail* still shows green. No metrics endpoint, no failure-streak detection, no dead-source detector (a channel that bans the session just logs warnings forever).

**Maintainability:** Clear module boundaries, consistent naming, ~3.2:1 test-to-feature file ratio. Counterweights: 1,067-line bot module mixing UX, delivery, admin, and stats; duplicated scheme tables; duplicated delivery functions (`deliver_updates` vs `deliver_updates_active` — near clones); reasoning-comments left in production code (`ingest.py`, `crypto.py` "Actually decrypt.py uses…"); `clean` vs `reset` overlapping semantics; README drift (§11).

**Onboarding/runbook gaps:** No documented procedure for: session revocation recovery, S3 state corruption, Telegram 409 conflicts, GitHub Pages takedown, or bot DB migration. The factory-reset path is documented but its `bot_users` destruction is not flagged anywhere (F-11).

---

# 11. Documentation Assessment (drift catalog)

| Claim (README/docs) | Reality (code) | Impact |
|---|---|---|
| "49+ Telegram channels" | 85 `telegram_user` sources in prod config | Cosmetic |
| "12 format handlers" | 16 registered (`register_builtin.py`) | Cosmetic |
| "Quality Gates — CI/CD enforces linting, typing, and tests" | flake8 restricted to E9/F63/F7/F82 (syntax/undefined only); mypy with `ignore_missing_imports` | Misleading to reviewers (F-26) |
| `HUNTX_MAX_WORKERS` default "2" | CLI/orchestrator default 3; CI default 2 | Confusing triple-default |
| Quick start: `export TELEGRAM_TOKEN` then run with prod config | Prod config uses **only** `telegram_user` sources requiring API_ID/HASH/SESSION; TELEGRAM_TOKEN alone yields 85 validation failures (empty `${TELEGRAM_API_ID}` → pydantic int error → fatal) | New-user onboarding broken (F-23) |
| "Auto-Deploy — GitHub Pages frontend automatically updated with fresh catalog data" | Catalog "dev" tag scans stale repo-root `outputs_dev/`; repo `outputs/` not updated by pipeline | Core claim partially false (F-01) |
| Bot has "13 commands" | 14 handlers incl. undocumented `/admin` | Hidden admin surface should be documented internally |
| outputs_dev README text differs between CI reset ("48h rolling window") and CLI reset / code ("all-time cumulative") | `_export_dev_outputs` is all-time cumulative | Conflicting self-description |

`docs/USER_GUIDE.md` and `docs/DEVELOPMENT.md` exist (not fully audited line-by-line here); given the above drift rate, both should be re-validated after remediation.

---

# 12. Findings Catalog

Each finding: Evidence → Impact → Likelihood/Severity/Confidence → Remediation → Effort → Priority → Validation.

---

### F-01 — Output-path drift: CI commits directories the pipeline no longer writes 🔴 CRITICAL
- **Evidence:** CI runs `huntx --data-dir persist/data … run` → `paths.set_paths` → `OUTPUT_DIR = persist/data/outputs`, `DEV_OUTPUT_DIR = persist/data/outputs_dev` (`store/paths.py:41–58`; `orchestrator.py:83,178`). CI then `git add outputs/ outputs_dev/ …` (workflow line 231) — repo-root paths. `generate_site_data.py:19` defaults `DEV_DIR = Path("outputs_dev")` (repo root, stale). Repo-root `outputs/` contains files last touched by historical "Update outputs [skip ci]" commits.
- **Root cause:** A data-dir refactor (`persist/data`) was applied to the pipeline but not to the CI commit step or the site-data script defaults.
- **Impact:** Technical: committed outputs and the Pages "dev" catalog serve stale data indefinitely; the "No output changes" branch always triggers for pipeline outputs. Business: the product's public deliverable is silently wrong. Operational: debugging is misleading (artifacts in CI uploads are fresh; repo/site are not).
- **Likelihood:** Certain (structural). **Severity:** Critical. **Confidence:** High (path arithmetic verified end-to-end; the only uncertainty is whether an undocumented step copies `persist/data/outputs` → `outputs/` — none exists in the workflow).
- **Remediation:** Single source of truth: either point `git add` at `persist/data/outputs*` via a copy step, or pass `HUNTX_DEV_DIR`/export-dir envs consistently; delete repo-root output dirs from version control and publish artifacts exclusively via Pages/Releases (also fixes repo bloat).
- **Effort:** S. **Priority:** P0. **Validation:** After one CI run, `git log -1 -- outputs/` shows fresh commit (or dirs removed); `docs/catalog.json` "dev"-tagged entries carry current timestamps.

### F-02 — Shared MTProto StringSession across threads/processes risks AUTH_KEY_DUPLICATED and serializes ingestion 🔴 CRITICAL
- **Evidence:** All 85 sources reference `${TELEGRAM_USER_SESSION}` (config); each worker thread builds `TelegramClient(StringSession(self.session), …)` in `_client()` (`telegram_user/connector.py:88`), guarded by a per-session `RLock` acquired in `_client()` and released in `cleanup()` (lines 85–91, 516–524) — lock acquisition and release in different methods, released inside a `finally` that only runs per-client during cleanup, with `RuntimeError` on over-release swallowed. Additionally `/admin run` in the persistent bot process (different machine) uses the same session concurrently with CI runs (`bot/interactive.py:999–1014`).
- **Root cause:** One purchased/created user identity reused everywhere; thread-per-source design grafted onto a session designed for one connection.
- **Impact:** Security/Reliability: Telegram detects one auth key used from concurrent connections → `AUTH_KEY_DUPLICATED` → **session invalidated**; all 85 sources die until a human re-runs `make_telethon_session.py` and rotates the GitHub secret. Scalability: when the lock *does* work, MTProto ingestion is fully serialized (worker pool useless for 100% of prod sources). The cross-method lock pattern can also deadlock (worker crashes between acquire and cleanup → lock never released within the process; daemon threads abandoned by timeout hold it forever).
- **Likelihood:** High (two independent triggers: intra-process thread races on creation before lock acquisition ordering issues, and bot-vs-CI cross-process overlap). **Severity:** Critical. **Confidence:** High for the design hazard; Medium for the in-process race specifics (lock does serialize creation+lifetime when paths execute as written).
- **Remediation:** (1) One client per process, shared by all sources, iterated sequentially or via asyncio tasks on a single loop (Telethon supports concurrent requests on one connection); (2) forbid bot-triggered runs while CI is enabled, or move bot runs to a distinct session; (3) replace cross-method locking with a context manager owning the client lifetime.
- **Effort:** M–L. **Priority:** P0. **Validation:** Soak test with workers=4 over 85 sources; assert single TCP connection per session (Telethon connection logs); chaos-test bot-run + CI-run overlap in staging session.

### F-03 — Ingest holds a single SQLite write transaction for the entire source run 🟠 HIGH
- **Evidence:** `ingest.py run()`: `with self.state_repo.db.connect() as conn:` wraps connector iteration (network I/O, downloads, FloodWait sleeps) through final state update; `db.py.connect()` commits only at context exit.
- **Impact:** Reliability: crash/timeout loses *all* of a source's seen_files + offset while blobs persist (feeds F-13). Concurrency: SQLite allows one writer; a source in a 30-minute FloodWait holds the write txn (first write upgrades to RESERVED), starving other workers up to the 30 s busy timeout → cascading "database is locked" failures under load. (Mitigating nuance: writes occur per 100-item batch, so the txn is open with pending writes for long spans.)
- **Likelihood:** Medium-High. **Severity:** High. **Confidence:** High.
- **Remediation:** Commit per batch (open/close connection inside `_process_batch`, plus a final state-update txn); or use one connection but `conn.commit()` after each batch and after state update.
- **Effort:** S. **Priority:** P1. **Validation:** Kill -9 mid-source in test; assert previously flushed batches survive; run 4 workers against slow mock connectors and assert zero busy-timeout errors.

### F-04 — Hard-coded third-party private keys and decryption passwords in source 🟠 HIGH
- **Evidence:** `formats/common/crypto.py` lines 18–140 (3 RSA private PEMs), `TUT_PASSWORDS` (3 static passwords, PBKDF2 iterations=1000), NetMod AES-**ECB** key `_netsyna_netmod_`, SlipNet XOR-derived AES-GCM key, XXTEA port credited to "vpndecrypt-Lol".
- **Impact:** Legal: redistribution of reverse-engineered key material (anti-circumvention/IP exposure; due-diligence red flag). Security hygiene: permanent secret-scanner noise that trains the team to ignore alerts. Note these keys decrypt *inbound* content only; HuntX's own credential confidentiality is unaffected.
- **Likelihood:** Certain (present). **Severity:** High (for acquisition/compliance contexts; Medium for pure ops). **Confidence:** High.
- **Remediation:** Move keys to an optional, clearly-licensed plugin loaded from env/external file; document provenance; add secret-scanning allowlist only after externalization; obtain legal review if these formats are business-critical.
- **Effort:** S–M. **Priority:** P1. **Validation:** `gitleaks`/`trufflehog` run clean on the repo; formats degrade gracefully when key material absent (handler returns no records).

### F-05 — Bot admin authentication accepts spoofable usernames 🟠 HIGH
- **Evidence:** `bot/interactive.py:341–349`: `HUNTX_ADMINS` matched against numeric user_id **or** username.
- **Impact:** A released/renamed @username can be re-registered by an attacker, granting `/admin` → pipeline trigger (resource abuse, output manipulation timing) and DB prune (data destruction up to 15-day floor via dashboard buttons; arbitrary days via `/admin prune N`).
- **Likelihood:** Low-Medium (requires handle churn). **Severity:** High (full admin). **Confidence:** High.
- **Remediation:** Match numeric IDs only; log and alert on admin command use.
- **Effort:** S. **Priority:** P1. **Validation:** Unit test rejects username-only match; manual test with a username in `HUNTX_ADMINS`.

### F-06 — Orchestrator timeout (4.5 h) exceeds CI job timeout (3 h); state persist never runs on overrun 🟠 HIGH
- **Evidence:** `cli/main.py:117` `orchestrator.run(timeout=16200)`; workflow `timeout-minutes: 180`; `Persist state` is a late step in the same job.
- **Impact:** Any run exceeding 3 h is SIGKILLed: no S3 persist, no outputs commit, no Pages deploy; all ingest progress lost (compounded by F-03); next run repeats the same long fetch → potential permanent thrash on backlog-heavy days (exactly when fresh-start lookbacks are largest).
- **Likelihood:** Medium (fresh starts / FloodWait storms). **Severity:** High. **Confidence:** High.
- **Remediation:** Set orchestrator timeout to ~150 min; add a trap step (`if: always()`) for persist; persist state *before* delivery; consider per-phase budgets.
- **Effort:** S. **Priority:** P1. **Validation:** Induce a slow run in a fork; verify persist executes and state survives.

### F-07 — Cron workflow pushes to `main` with broad write permissions and rebase-retry 🟠 HIGH
- **Evidence:** workflow `permissions: contents: write`; commit step pushes `HEAD` to origin (main) with 5 retries and `git pull --rebase || true`.
- **Impact:** Supply chain: any code executed in the job (incl. unpinned pip deps, F-25) holds repo-write + Pages tokens + all secrets. Integrity: rebase-retry on a busy repo can interleave bot commits with human work, and `|| true` on rebase failure leads to pushing a stale base or repeated failures; `[skip ci]` history pollution already dominates `git log`.
- **Likelihood:** Medium. **Severity:** High. **Confidence:** High.
- **Remediation:** Publish artifacts to a dedicated `outputs` branch or GitHub Releases; split deploy into a minimal-permission job; pin actions by SHA; pip with `--require-hashes` lockfile.
- **Effort:** M. **Priority:** P1. **Validation:** `main` history free of bot commits; job token scopes minimized (inspect `GITHUB_TOKEN` permissions in run logs).

### F-08 — Unverified content redistribution + no bot rate limiting 🟠 HIGH
- **Evidence:** §7.2; `_send_latest_to_user`/`_on_latest` unbounded per-user; auto-registration on every command; ZIP passthrough comment in `content_type.py`.
- **Impact:** End users can receive malicious proxy endpoints (traffic interception) or malware-bearing ZIPs (`opaque_bundle`); abusive users can flood-ban the bot identity, breaking delivery for everyone.
- **Likelihood:** Medium. **Severity:** High. **Confidence:** High for the mechanism; Medium for active exploitation.
- **Remediation:** Per-user token-bucket on commands; cap files per `/latest`; scan ZIP members against the same magic-byte filter; add a visible "configs are unverified" disclaimer; consider connectivity/abuse screening before publication.
- **Effort:** M. **Priority:** P1. **Validation:** Load-test bot with scripted user; ZIP containing PE is rejected end-to-end.

### F-09 — getUpdates 409 conflict between pipeline connector and persistent bot on shared token 🟠 HIGH
- **Evidence:** `publish.py:67` and `cli/main.py` fall back `PUBLISH_BOT_TOKEN or TELEGRAM_TOKEN`; `TelegramConnector` polls `getUpdates` on `TELEGRAM_TOKEN`; the persistent GatherX bot long-polls the publish token. If `PUBLISH_BOT_TOKEN` is unset, one bot token is polled by two consumers → Telegram returns 409 to one; updates are also *consumed* (offset-acked) by whichever wins, starving the other.
- **Likelihood:** Medium (config-dependent). **Severity:** High when it occurs (silent ingestion loss or bot outage). **Confidence:** High.
- **Remediation:** Hard-require distinct tokens when both subsystems are active; detect 409 and fail loudly.
- **Effort:** S. **Priority:** P1. **Validation:** Startup assertion test; integration test with both pollers.

### F-10 — Bot-embedded pipeline uses divergent path/config defaults 🟡 MEDIUM
- **Evidence:** `_run_pipeline_blocking` reads `HUNTX_CONFIG` (default `config.yaml`) and never calls `paths.set_paths` → uses `./data` defaults, while CI uses `persist/data`; lock file likewise differs.
- **Impact:** Bot-triggered runs build against a *different* state DB and output dirs than CI; results diverge silently; combined with F-02, also shares the session.
- **Remediation:** Centralize runtime config; have the bot reuse the exact CLI entry with explicit dirs. **Effort:** S. **Priority:** P2. **Validation:** Bot-triggered run writes to the same DB (row counts move).

### F-11 — Factory reset destroys `bot_users` (all subscribers) with no warning or backup of users 🟡 MEDIUM
- **Evidence:** `bot_users` lives in `state.db` (`interactive.py:128`); CI reset `rm -rf persist/state.db` and `aws s3 rm` (state.db backed up to `.bak`, archive not); CLI `reset` backs up DB locally then deletes.
- **Impact:** A maintenance reset silently unsubscribes every user — unrecoverable audience loss if `.bak` is also wiped later.
- **Remediation:** Move bot tables to a separate DB file excluded from reset, or export users pre-reset. **Effort:** S. **Priority:** P2. **Validation:** Reset in staging preserves user table.

### F-12 — Timed-out ingestion threads keep running through later phases 🟡 MEDIUM
- **Evidence:** `orchestrator.run` raises `TimeoutError` while joining; threads are daemons (`daemon=True`, line 450) and are never cancelled; Phases 2–4 proceed.
- **Impact:** Zombie writers mutate `seen_files` during/after build & cleanup → next run's `seen_file_cutoff_id` delta and `prune_processed` race the writers; nondeterministic artifacts.
- **Remediation:** Cooperative cancellation flag checked in `_worker`/connectors; or pass a `deadline` (the ingest pipeline already supports one — it is simply never passed). **Effort:** S. **Priority:** P2. **Validation:** Timeout test asserts threads observe deadline within one batch.

### F-13 — Orphaned raw blobs are unreclaimable; dev manifest written non-atomically 🟡 MEDIUM
- **Evidence:** Blob written (`raw_store.save`) before txn commit (F-03); both prune paths (`prune_processed`, `prune_by_hashes`) operate only on hashes known to the DB; orphans (blob exists, no row) are never enumerated. `_manifest.json` via `Path.write_text` (orchestrator.py:221) despite `utils/atomic.atomic_write` existing.
- **Impact:** Unbounded disk creep across crashes (slow on CI ephemeral runners, real for systemd deployments); manifest corruption resets all-time dedup (mass re-announcement of old proxies as new).
<truncated 16883 bytes>

NOTE: The output was truncated because it was too long. Use a more targeted query or a smaller range to get the information you need.