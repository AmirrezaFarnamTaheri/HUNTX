# HUNTX — Final Consolidated Forensic & Migration Report

**Date:** 2026-08-17 · **Repo:** `D:/GitHub/HUNTX` (`github.com/AmirrezaFarnamTaheri/HUNTX`) · **HEAD inspected:** `main @ 8ffd830` (origin was +1: `473d8f9`)
**Method:** 9-phase forensic audit (discovery → deep analysis → capability extraction → porting analysis → architectural improvements → duplication/consolidation → parity/gap analysis → knowledge preservation → implementation roadmap). Read-only investigation; the only files written are this report set.
**Companion reports:** `01_pipeline_core.md` · `02_bot_cli_config.md` · `03_formats_connectors_publishers.md` · `04_go_ci_scripts.md` · `05_git_archaeology_hidden.md` · `06_docs_knowledge.md` (this directory). All citations are verified `file:line` unless marked otherwise.

**Live-verification status legend** (applied to defect catalog §9 and appendix §A):
- ✅ **VERIFIED** — confirmed by reading exact source lines or running grep/shell against the live repo
- 🔍 **INFERRED** — derived from surrounding code or transitive analysis (sound but not grep-confirmed)
- ⚠️ **STALE-RISK** — claim accurate at inspection time; adjacent code changes may invalidate

> **Assumption flag.** No external target system was named for this investigation. The consolidation target is therefore assumed to be **HUNTX's own next-generation consolidation track** — i.e., the repo's stated direction (conductor `next_gen_architecture_20260725` track, "one Python source of truth" per `docs/DONOR_PR_ABSORPTION_LEDGER.md`, the dormant-but-merged next-gen engines). Every recommendation below is phrased as "consolidate into the live production path / the next-gen track." If a different target system was intended, the classification logic still applies; only the destination changes.

---

## 0. Executive summary

HUNTX is a 6-month-old, ~28k-LOC (15k Python pipeline + 10.3k tests + 2.5k Go release-plane + 1.6k scripts) Telegram-sourced proxy-config aggregation system. It ingests 85 Telegram sources via MTProto user sessions, parses 16 format handlers (19 proxy URI schemes), builds 12 routed formats + 3 derivatives, publishes to a Telegram channel, delivers to bot subscribers, and ships verified artifacts to GitHub Pages + S3-backed immutable "generations" — all driven by a 2-hourly zero-budget GitHub Actions cron.

**The system is operationally mature and unusually well-hardened** (durable publication ledger, content-addressed stores, atomic writes everywhere, ack-fenced ingestion, fail-closed secret gates, workflow-as-tested-code). But the investigation found a consistent structural pattern: **the codebase carries three layers of debt around every major subsystem** —

1. **A live path defined by monkey-patches, not class source.** Six import-time patch installers (`runtime_resilience`, `transform_contract`, `dev_manifest_contract`, `migration_safety`, `repo_hardening`, `consumer_reconciliation` + telegram `hardening`) replace or wrap core methods. Reading the classes alone misdescribes production (01 §D2, 02 §3.4).
2. **Merged-but-dormant next-gen capability.** The entire conductor "Next-Gen Architecture" track (UnifiedOrchestrator, circuit breaker, proxy scoring, geo routing, self-healing daemon, streaming chunk parser, latency benchmarker) is merged, exported, and test-green — and has **zero production callers** (01 §D1, 05 §H1/H3).
3. **Half-built governance features.** The "secure" publication tier has no verdict writer and silently builds zero records (01 §D4); the durable source-trust model is dead while a config-enum twin is live (01 §D5); the bot approval gate exists with **no approval workflow anywhere** (02 §7.1).

Plus **live-grep-verified defects**: a subscriber-loss bug on every `clean`/`reset` (✅ main.py:226-236 confirmed missing `approved` column in CREATE TABLE — F10, 02 §7.2); a CLI `prune` that can delete live raw blobs (✅ main.py:446 confirmed no orphan-hash guard — 02 §7.4); hardcoded decryption passwords in source (✅ crypto.py:128-130,241 read verbatim — 03 §C1); a verdict writer that is **defined but never called anywhere in src/** (✅ `upsert_record_verdict` grep returns exactly one line: its own definition — 01 §D4); no approval handler despite the `approved` gate (✅ bot/ grep finds only schema/WHERE, never a SET — 02 §7.1); two committed `.exe` binaries of an explicitly-rejected module (04 §1, F15); inverted Go test coverage — CI tests only dead code, live release plane has zero `_test.go` files (04 §2); 5.2 GB of git bloat with 436 tracked runtime files (F11); unbounded state-DB growth because the only auto-prune path is dead code (01 §D3).

**Headline numbers:** 909 commits / 1 human owner / 7 AI-agent identities · 498 tests passing (2 env-dependent failures, 1 stale perf test, 1 flaky) · 16 format handlers (12 routed) · 19 URI schemes · 15-table SQLite schema at user_version 10 · 5 CLI subcommands (README says 4) · 85 sources (README says 49+) · 50 branches (31 deletable, 2 salvageable fixes, 2 dead state-mirror branches causing most history bloat) · 30+ undocumented env knobs.

**The roadmap (§10) sequences 26 implementation-ready tasks** in 5 waves: stabilize (verified bug fixes + secret externalization), inline the patches, wire-or-excise the dormant features, consolidate duplicates, then hygiene (repo weight, docs, branch cleanup). Estimated total: ~3–4 engineer-weeks for waves 1–3; waves 4–5 can proceed in parallel at lower priority.

---

## 1. Phase 1 — Complete discovery & architectural map

### 1.1 Repository composition (evidence F2–F7)

| Subsystem | Path | LOC / size | Role |
|---|---|---|---|
| Python package | `src/huntx/` | 15,003 LOC (core 3,220 · formats 2,334 · state 2,266 · connectors 1,704 · pipeline 1,629 · bot 1,358 · cli 718 · store 643 · utils 453 · config 365 · publishers 210) | The product |
| Tests | `tests/` | 10,306 LOC / 95 files (+ `tests/perf/`) | Executable spec; strong |
| Go release plane | `cmd/huntx-tools/` + `internal/{outputverify,releasemanifest,runtimegen,sitegen}` | 1,278 LOC, 0 tests | LIVE in CI — output verification, immutable generations, site catalog |
| Go engine (orphaned) | `cmd/huntx-engine/` | 809 LOC + 5 test files, own `go.mod` (`go 1.26` — unbuildable in CI's 1.23) | Rejected track; still in-tree + 2 committed `.exe` (F15) |
| Go collector (dormant) | `src/huntx/connectors/v2ray_collector/` | 648 LOC, own module | Wired but unconfigured in prod |
| Scripts | `scripts/` | 1,612 LOC / 9 files | Snapshot assembly, checkpoint repair, health reporting, session bootstrap |
| CI | `.github/workflows/` | 5 workflows + dependabot | 2h cron production, PR gate, publish control plane, 2 gates |
| Docs | `docs/`, `conductor/`, `README.md`, `full_audit_report.md` | ~2,600 lines | Mixed freshness (§8) |
| Runtime/data | `data/` 51 MB logs · `data_archive/` 811 MB (410 tracked) · `outputs*/` · `persist/` · `temp_*` | F7, F16 | Prod state lives in CI/S3; local is dev residue |
| Analysis caches | `.cocoindex_code` 409 MB, `.codegraph` 11 MB, `.code-review-graph` 6.6 MB, `.serena`, `graphify-out` | untracked (F13) | Prior tool runs; no human findings except graphify raw graph (no report file) |

**The "754 .go files" mystery is resolved (F5→F6):** 737 are the local Go module cache under `.tmp/gomod/` (gitignored); the project has exactly 17 Go files.

### 1.2 Dependency & runtime hierarchy

```
Entry: pyproject.toml:31  huntx = huntx.cli.hardened_main:main
  hardened_main.main() → apply_runtime_resilience() [6 monkey-patch installers]
                       → legacy.main() with legacy._cmd_run replaced
  _cmd_run: OptimizedHardenedOrchestrator + GovernedBuildPipeline
            + reconcile_configured_bot_consumers + run-health gate + auto-deliver

Pipeline stages (all bounded, deadline-accounted):
  INGEST   telegram_user×85 → WindowedTelegramUserConnector → PersistentIngestionQueue
           (LIFO epoch windows, lease tokens, BEGIN IMMEDIATE) → IngestionPipeline
           (dedup seen_files + content-addressed RawStore)
  TRANSFORM OptimizedTransformPipeline (ThreadPool parse, decide_format router,
           per-file record caps, atomic record+observation commits)
  BUILD    GovernedBuildPipeline (per-route policy, single-flight query reuse)
           → BuildPipeline (dedup query, per-format locks, ArtifactStore, derivatives)
  PUBLISH  PublishPipeline (sha256 pinning, durable publication intents,
           per-destination state machine incl. unknown_outcome manual-reconcile lock)
  EXPORT   outputs/ (3-day retention) + outputs_dev/ (cumulative _manifest.json)
  HEALTH   evaluate_run_health → fatal/degraded/success → exit code contract

CI plane (huntx.yml, 699 lines):
  validate → restore(S3 generation, OIDC) → run(105m watchdog) → package(Go verify-output
  + site-data, safety-net fallback) → checkpoint(SQLite repair + immutable generation)
  → persist(S3, pointer-last) + deploy-pages
  then workflow_run followers: publish-generated-outputs (generated-outputs branch
  + 12-path main mirror) + 2 activity gates
```

### 1.3 Integration points
- **Telegram MTProto** (Telethon StringSession; all 85 prod sources) · **Telegram Bot API** (publisher + GatherX bot; stdlib-only multipart) · **GitHub Actions** (the entire production model) · **S3** (immutable state generations; OIDC + static-key fallback) · **GitHub Pages** (artifact SPA reading `catalog.json`) · **SQLite WAL** (single state DB, user_version 10).

---

## 2. Phase 2 — Deep forensic analysis (what actually runs)

Full call chains, schema, and data-flow in `01_pipeline_core.md`. The findings that matter for consolidation:

### 2.1 Orchestrator lineage — 4 classes, 1 live path (01 §2)
| Class | Status |
|---|---|
| `Orchestrator` (core/orchestrator.py:39) | Live as base: wiring, exports, ingest-one-source. `_run_async_legacy` (:470-719, ~250 LOC) is dead — and is the **only automatic caller of `repo.prune_old_data`** |
| `HardenedOrchestrator` (:38) | Live: authoritative stage machine `_run_hardened` |
| `OptimizedHardenedOrchestrator` (:20) | **Production class**, but its own `_run_hardened` and `_canonical_ingestion_sources` are *shadowed at runtime* by runtime_resilience.py:299-304 patches |
| `UnifiedOrchestrator` (:22) | **Dead prototype** of the next-gen track; skips ingestion entirely; instantiates never-called engines |

### 2.2 Production behavior = class source + 6 monkey-patches (F12)
`telegram/hardening.install_telegram_connector_hardening` (ack fencing) · `core/dev_manifest_contract:75` (dev-export normalization) · `core/transform_contract:15` (deadline wrapper) · `state/consumer_reconciliation:169` · `state/migration_safety:50` (v10 verdict-sweep guard) · `state/repo_hardening:229` (atomic record_file + bot-consumer methods) · plus `runtime_resilience.apply_runtime_resilience`. The shadowed class methods **diverge semantically** from their patches (e.g., the class version never assigns `self.config.sources = ingestion_sources`; only the patch does — runtime_resilience.py:230). **Any refactor that reads only the classes will regress production.**

### 2.3 State schema (state/schema.sql, 215 lines, user_version 10)
15 tables / 20 indexes. Live: `source_state`, `seen_files`, `records`, `published_artifacts`, `publication_intents`, `publication_deliveries`, `telegram_bot_updates`, `telegram_bot_consumers`, `bot_users`, `bot_delivery_checkpoint`, `bot_delivery_items`, `ingestion_campaigns`, `ingestion_work_items`. **Dead in production:** `source_lifecycle` (trust model, tests-only), `record_verdicts` (no writer — see §4.2). Migrations v1–v10 each have postcondition checks; v10 is a VMess canonicalization **re-key** of `records.unique_hash` — the same canonical form used by npvt parsing and the outputs_dev manifest (three subsystems, one identity function; §9 knowledge #4).

### 2.4 Durability contracts worth preserving (they are the product's spine)
- WAL + `synchronous=FULL`, busy_timeout 30s, FK ON (db.py:52-55)
- Content-addressed RawStore with digest re-verification on disk (raw_store.py:46-70)
- One-transaction contracts: page items + queue checkpoint (windowed_ingest.py:118-133); records + observation flips (repo.py:358-370)
- Lease-token-guarded queue transitions, rowcount!=1 ⇒ RuntimeError (ingestion_queue.py:249-250)
- Publication: payload sha256 must equal artifact_hash; `unknown_outcome` blocks auto-resend until manual reconciliation (publish.py:68-70,171-179)
- S3 generation: payload → manifest → remote cmp → `current.json` pointer **last** (04 §9.3; order pinned by test)

---

## 3. Phase 3 — Capability extraction (complete register)

### 3.1 LIVE capabilities (production-reachable)
Hardened run path with LIFO windowed ingestion · 16 format parsers (12 routed: npvt, npvtsub, conf_lines, ovpn, npv4, ehi, hc, hat, sip, nm, dark, opaque_bundle; + derivatives b64sub/decoded.json/singbox.json) · 19-scheme URI validation with SSRF-grade host rejection (proxy_uri_validator.py) · sing-box 1.14 outbound renderer (common/singbox.py, 603 LOC) · 4 crypto stacks (HAPP RSA 3 key-gens, SlipNet AES-GCM, TUT/SKS/TMT PBKDF2, NetMod ECB) · publication ledger + Telegram publisher with retry/429/unknown-outcome semantics · GatherX bot (13 public commands + hidden `/admin`, per-content delivery resume, FloodWait bounds) · run-health gate + degraded-success semantics · immutable S3 generations + safety-net publication + Pages deploy + generated-outputs branch/main mirror control plane · checkpoint DB-repair script · consumer reconciliation with token fingerprints.

### 3.2 DORMANT (merged, tested, zero production callers) — revival candidates
| Capability | Location | Revival value |
|---|---|---|
| `StreamingChunkParser` (64 KB chunks, <50 MB RAM design) | formats/streaming.py:10-166 | **High** — directly fixes C4 (npvt's unbounded whole-file b64 decode) |
| `LatencyBenchmarker` (async, URI-aware) | core/latency_benchmarker.py | **High** — completes conductor track 2's "latency gate >3000 ms"; small, tested |
| `SelfHealingDaemon` (SQLite-durable, backoff 5m/15m/1h/6h, purge 48h) | core/self_healing.py | **Medium** — durable twin of Go healing; needs a probe source |
| `ProxyScoringEngine`, `AsyncCircuitBreaker`, `GeoRoutingEngine` (20-TLD taxonomy) | core/scoring.py, resilience.py, geo_routing.py | **Medium** — tested; wire into build/publish path or archive |
| `UnifiedOrchestrator` | core/unified_orchestrator.py | **Low as-is** (skips ingestion/export) — use as integration shell only after the engines are wired |
| Async `acquire_session_lease` heartbeat protocol | core/session_lease.py:170-220 | Low — prod uses plain file lock on the same path |
| `send_freshness_alert` (bot) | bot/delivery.py:24-48 | Medium — spec-complete, dead; needs a scheduler caller |
| Bot-API `TelegramConnector` + ack-fencing hardening | connectors/telegram/* | Low — schema-supported but 0 bot-token sources configured |
| `V2RayCollectorConnector` (Go scraper) | connectors/v2ray_collector/ | Low — one config line from production, but needs vendored deps + real latency measurement |
| `RejectsStore`, `release_manifest.py` (Python), `scripts/{build_release_manifest,generate_site_data,runtime_generation}.py` | store/, scripts/ | Python twins kept as testable specs of the Go release plane (deliberate dual-track, 04 §8) |
| XXTEA-with-custom-delta port | formats/common/crypto.py:174-225 | None — dead port from "vpndecrypt-Lol"; archive |
| `detect()` content-detection hooks | slipnet.py:149-157, hat.py:27-36 | None — vestige of an earlier dispatch design |

### 3.3 HALF-BUILT features (schema/gate present, producer/workflow absent)
1. **"Secure" publication tier** — `record_verdicts` table + `get_records_for_governed_build` + verdict model + latency prober all exist; **nothing ever writes verdicts** ⇒ a `secure` route silently builds zero records (01 §D4).
2. **Durable source trust** — `source_lifecycle` + `record_source_event`/`get_source_lifecycle` are tests-only; production uses the config-enum `trust_state` (01 §D5).
3. **Bot user approval** — `bot_users.approved` gate exists; **no `/approve` handler, no runbook, nothing in src/ ever sets approved=1** ⇒ auto-delivery is dead on fresh deploys until manual SQL (02 §7.1).
4. **Conductor track 1 runtime integration** — all 4 deliverables exist + tested; none wired (05 §5).

### 3.4 HIDDEN / undocumented surface
- CLI: `prune` subcommand (undocumented); `--config/--data-dir/--db-path` globals; `interactive.py:372-383` dev `__main__` backdoor; `HUNTX_BOT_NO_PUBLISH`, `HUNTX_RUN_SUMMARY_PATH` knobs (02 §6).
- Bot: `/admin` deliberately omitted from the command menu; approval = manual SQL (README:113).
- CI: anti-fake gates that verify real Telegram activity via diagnostics markers (05 §H7); `workflow_dispatch` reset requiring literal `RESET-HUNTX-STATE`.
- Disk: `temp_bot_init/` + `temp_data_interactive/` each hold a **live `bot.session` Telethon credential** (untracked, gitignored, content not read — F16); stash@{0} holds a **prior 2026-08-16 forensic report**; stash@{1} holds the Jul-25 next-gen WIP incl. binaries.
- Secrets-in-source: tut/sks/tmt fallback passwords, SlipNet XOR key constants, NetMod key (03 §C1).
- TODO/FIXME census: **zero markers** in src/cmd/internal/scripts (05 §H21) — the codebase is marker-clean; all known debt lives in this report instead.

---

## 4. Phase 4 — Porting & absorption classification

Every discovered capability, classified. Rationale + evidence per row in the companion reports.

### 4.1 ABSORB (wire dormant capability into the live path)
| Item | From | Into | Rationale / risk | Value |
|---|---|---|---|---|
| A1 StreamingChunkParser | formats/streaming.py | npvt/npvtsub transform path (large-file branch) | Tested spec; kills unbounded-memory C4; conductor deliverable finally earning its keep | High / low risk |
| A2 LatencyBenchmarker | core/latency_benchmarker.py | New build-stage probe feeding `record_verdicts` (see A3) | Completes track-2 latency gate; async, tested | High / med risk |
| A3 Verdict-producing stage | verdicts.py + verdict_store.py | Transform (syntax verdicts) + probe stage (probe verdicts) | Makes `secure` tier real instead of a silent zero-record trap; or EXCISE the tier (decision task T10) | High |
| A4 Lifecycle trust events | state/lifecycle.py | Ingest outcomes (failure/nonempty/valid) | Gives the durable trust model a writer; else drop the table (T10) | Med |
| A5 Bot approval workflow | new `/approve`/`/deny`/`/list` handlers | bot/admin.py | Unblocks the entire delivery promise; gate already exists | **Critical** |
| A6 Freshness alert caller | delivery.py:24-48 | run-health post-step or `/admin` button | Spec-complete dead code; one caller away | Low |
| A7 DB-lock + MTProto disconnect-leak fixes | branches `fix-db-locking-in-ingest-*` (`38e791f`, `c59c815`) | ingest/windowed path | **Unmerged real bug fixes** verified not ancestors of main; re-test then port (05 §3.5) | Med |
| A8 Ultra-resilient safenet residue | `codex/ultra-resilient-partial-workflows` (27 commits) | run-health/publish | Only a slice landed via #65; review for last-known-good release + degradation metrics (05 §7.3) | Med |

### 4.2 DIRECT PORT (adopt as-is)
- `scripts/make_telethon_session.py` bootstrap procedure → any new deployment (it is the only session-rotation path).
- `_coerce_retry_after` (publisher.py:44-75) → shared utils (untrusted-API-value coercion done right).
- `utils/atomic.py` + `utils/content_type.py` zip-bomb/zip-slip bounds → any file-handling surface.

### 4.3 ADAPT & MODERNIZE
- **Inline all 6 monkey-patches into their classes, delete shadowed copies** (T2). The patches were a deliberate mid-production strategy (05 §7.1) but are now the debt ceiling; tests pin the behavior, so inlining is safe with the existing suite.
- Collapse 4 orchestrators → 1 class (keep Hardened stage machine + Optimized worker; delete `_run_async_legacy` after moving `prune_old_data` into cleanup).
- Merge the two transform loops (~120 LOC × 2, 01 §D7); unify the 3 CLI run implementations (01 §D8); single `outputs/` writer (01 §D6).
- `paths.py` dual model (module globals vs frozen `RuntimePaths`) → `RuntimePaths` only.

### 4.4 MERGE with existing implementation
- Go vs Python twins (04 §8): keep the **deliberate dual-track** for the release plane (Go executes in CI, Python is the unit-testable spec — `runtimegen`/`releasemanifest`). For everything else Python is canonical: archive Go `stream/georoute/healing/benchmark` (strict subsets of tested Python twins; georoute has drifted: 15 vs 20 TLDs).

### 4.5 ARCHIVE (preserve, stop building)
- `cmd/huntx-engine/` + both `.exe` (explicitly rejected in ledger:141; `go 1.26` unbuildable; nested module never compiled by CI). Move to an `archive/` dir or a tag; delete the binaries from the tree (history keeps them).
- `UnifiedOrchestrator` if A1–A3 land via the live path instead (its only unique value is as an integration shell).
- `scripts/systemd/mergebot.service` (pre-rename; keep as the documented VM-deployment shape if ever needed — rename to huntx).
- Donor branches `dc3d795`/`443d169` **kept frozen** until the ledger retires (they are cited evidence).

### 4.6 DISCARD
- `decrypt_xxtea` (zero callers) · `FormatRegistry.get_instance` singleton (config-validation compat) · publish hash-cache remnants + `is_artifact_published` (01 §D9) · `cli/commands/run.py` orphan · `scripts/{build_release_manifest,generate_site_data}.py` dead twins · `.data/vectors/` empty dir · 31 merged-lingering branches (05 §3.1) · `huntx-state`/`mergebot-state` branches after blob extraction (destructive — maintainer decision, §12).

---

## 5. Phase 5 — Architectural improvements worth absorbing (independent of features)

Patterns this codebase invented or perfected that should survive into any successor system:

1. **Workflow-as-tested-code** — `tests/test_workflow_resilience.py` + `test_generated_output_*` pin action SHAs, timeout literals, upload ordering, permission boundaries as pytest assertions (04 §9.9). Rare and valuable.
2. **Layered watchdog + degraded-success semantics** — internal budget < TERM < kill < job < cron; exit 124/137/143 + verified checkpoint = degraded, not fatal (04 §9.1-2; docs/RUN_HEALTH.md).
3. **Immutable generation protocol** — payload→manifest→cmp→pointer-last; reset backs up the pointer first (04 §9.3).
4. **Safety-net publication** — snapshot last-good outputs pre-run; republish them if fresh output fails independent verification (04 §9.5).
5. **Per-content delivery resume** — `(user_id, artifact_hash)` ledger written immediately after each send ⇒ crash-safe at file granularity (02 §2.4).
6. **Ack-fencing** — yielded/acknowledged ledgers so offsets only advance past durably-processed items; failed updates stay replayable (03 §4, telegram/hardening.py). The *pattern* is excellent; the monkey-patch delivery is the debt.
7. **Predicate-purity discipline** — per-item validators never raise; documented as a hard-won lesson in proxy_uri_validator.py:82-88.
8. **Bounded-resource builders** — declared-size pre-filter + real-bytes re-check + explicit drop logging (opaque_bundle.py:81-106).
9. **Dual sync/async connector contract** — `AsyncSyncIterator` + running-loop-safe `run_sync` (connectors/base.py:19-65).
10. **Fail-loud vs fail-soft env policy, documented** — YAML `${VAR}` refs fail loud; runtime tuning knobs fail soft with bounds (config/env_expand.py vs utils/env.py:11-15).
11. **Secret redaction at the logging layer** with `record.args = ()` re-format prevention (logging_conf.py:8-36); token fingerprints instead of tokens in DB (consumer_reconciliation.py:158).
12. **Anti-fake CI gates** — the project defends against its own CI faking runs (05 §H7).
13. **Cumulative-identity preservation** — rendered legacy history as authoritative migration input; earliest-`first_seen` merge; fail-closed on unrecoverable legacy (04 §9.6).
14. **Reproducible builds** — `PYTHONHASHSEED=0`, `--generated-at` override, deterministic sorted walks, `pip --require-hashes` (340 hashes).

---

## 6. Phase 6 — Duplication & consolidation strategy

| Domain | Duplicates | Best implementation | Strategy |
|---|---|---|---|
| Orchestration | 4 classes + patch layer | Hardened stage machine + Optimized worker + patches' semantics | Inline patches → 1 class (T2/T3) |
| Transform loop | transform.py vs optimized_transform.py | optimized (adaptive batch) | Merge, parameterise (T5) |
| CLI run | main.py vs hardened_main.py vs commands/run.py | hardened_main | One command; delete orphan (T6) |
| Outputs writing | BuildPipeline.save_output vs _export_outputs | export (owns retention) | Single writer + one naming scheme (T7) |
| Stream parsing | Go stream vs Python formats | Python | Archive Go (T20) |
| Geo routing | Go georoute (15 TLDs) vs core/geo_routing.py (20) | Python | Archive Go |
| Self-healing | Go healing (in-mem) vs core/self_healing.py (SQLite) | Python | Archive Go |
| Benchmarking | Go benchmark (sync TCP) vs latency_benchmarker.py (async) | Python | Archive Go; wire (A2) |
| Release plane | Go runtimegen/releasemanifest/sitegen vs Python twins | **Both, deliberately** (Go executes, Python specifies/tests) | Keep dual-track; add native Go tests (T18) |
| Site data | Go sitegen vs scripts/generate_site_data.py | Go | Delete Python twin |
| b64 decoding | already consolidated into common/b64.py | — | Done (pattern noted) |
| State pruning | admin prune (guarded) vs CLI prune (unguarded) | admin's orphan-hash guard | Port guard into CLI prune (T4) |
| Trust models | config enum vs source_lifecycle | decide (T10) | Wire lifecycle events or drop table |
| Verdict pipeline | verdict model + store + prober, no writer | decide (T10) | Complete or excise `secure` tier |

Missing among duplicates (functionality no variant has): a verdict *producer*; an approval *workflow*; a signal handler anywhere in CLI/core (02 §3.7); native Go tests for the live release plane.

---

## 7. Phase 7 — Feature parity & gap analysis

### 7.1 README/docs claims vs reality (06 §4)
| Claim | Reality |
|---|---|
| 49+ sources | **85** (config.prod.yaml + constants.py:10) |
| 12 formats | 16 registered; 12 routed; +3 derivatives |
| 20+ protocols | 19 URI schemes (~accurate) |
| 4 CLI commands | **5** (`prune` undocumented) |
| deny-by-default bot access | Delivery gate yes; on-demand commands ungated; **no approval workflow** |

### 7.2 Prior-audit status (the repo audits itself; this is the current truth)
- June `full_audit_report.md` (F-01…F-28): output-path drift **remediated** (entire publish control plane exists for it); shared-session AUTH_KEY_DUPLICATED **remediated by design**; F-04 embedded keys **partially open** (HAPP→env done; tut/sks/tmt/slipnet/netmod still hardcoded); F-09 409 conflict **remediated**; timeout inversion **remediated**.
- `HUNTX_AUDIT_CLOSURE.md` still-Open items to inherit: D-02 SIP002 plaintext fixtures, D-05 Hysteria2 obfs aliasing fixtures, D-07 TLS-verification-bypass policy at build, D-12 lexical NPVT extraction, SYN-01 typed proxy IR, SYN-06 native client gates, SYN-08 observability contract.
- `MASTER_FORENSIC_COMPENDIUM.md` is **marketing-grade, not forensic-grade** (lists nonexistent decoders `v2ray`/`clash`, claims the benchmarker is integrated, wrong schema names) — do not trust as a source (06 §2).
- `docs/GENERATED_OUTPUTS_MODEL.md` is the **current authority** for publication; CONVERGENCE_2026-07-27's "never commit outputs to main" invariant is stale (deliberate, tested policy drift via PR #75).

### 7.3 Gaps vs a production-grade target
1. Approval workflow (§4.1 A5) — biggest operational gap.
2. Secret provisioning inventory — scattered across workflows/README/USER_GUIDE; no single checklist (06 §8.2).
3. Disaster recovery runbook — S3 restore tested; "rebuild from nothing" (session re-bootstrap, approval re-grant) undocumented.
4. Env-var reference — ~30 knobs, no consolidated table.
5. Data lifecycle policy — data_archive 811 MB tracked; outputs_dev unbounded growth acknowledged, no policy.
6. Signal handling — none in CLI/core.
7. Go test coverage for the live release plane — zero `_test.go` in `internal/`+`huntx-tools`.
8. Observability — structured run-summary exists; no metrics/tracing surface (SYN-08 self-acknowledged).

---

## 8. Phase 8 — Knowledge preservation (institutional register)

Must survive any migration (full detail: 06 §7, 03 §10, 04 §9, 05 §7):

1. **vmess canonical identity** — remark-stripped sorted-key JSON canonicalization shared by npvt parsing, DB v10 re-key, and outputs_dev manifest. Changing it silently re-keys the dedup universe.
2. **Decoder provenance & crypto parameters** — Slipstream schemas V1–V28 (pipe-separated field orders, boolean set, AES-GCM layout `[version:1][iv:12][ct+tag]`, XOR key assembly); HAPP 3 key generations by link prefix; TUT/SKS/TMT `salt.iv.ct` PBKDF2-SHA256 **1000 iterations** matching pycryptodome, tag = last 16 bytes; NetMod AES-ECB key + proto-prefix preservation; ss URI duality (both base64 forms); mid-line URI extraction requirement. Sources cited only in code comments: Pantegnos(-main), Slipnet decoder.html, vpndecrypt-Lol, smgo.
3. **Why patches, not refactors** — hardening wave shipped invariants against a frozen orchestrator mid-production (05 §7.1).
4. **Layered watchdog / degraded-success / immutable generation / safety-net / cumulative-bootstrap / main-mirror safety** — 04 §9 (all operational know-how embedded in workflows + scripts, documented in docs/RUN_HEALTH.md + GENERATED_OUTPUTS_MODEL.md).
5. **Session bootstrap procedure** — make_telethon_session.py → `TELEGRAM_USER_SESSION` → per-session lock identity; the only rotation path.
6. **Approval is manual SQL** (README:113) — will be lost if the bot is redeployed without a runbook.
7. **Donor governance** — frozen donor SHAs `dc3d795`/`443d169` are ledger evidence; deleting those branches breaks citations.
8. **Repo founding provenance** — ROADMAP.txt containing the AI's own refusal text (`git show 1a2a738:ROADMAP.txt`); GATHEREX + smgo/compare sibling merges — HUNTX is already a 3-repo consolidation.
9. **Windows ops lore** — pytest `--basetemp` isolation; flake8 config lives only in `.flake8`; conflict-marker sweep after stashes.
10. **Anti-fake gates rationale** — defense against the CI faking its own runs.
11. **Unmerged fixes at risk** — DB-lock/MTProto-leak fixes (`38e791f`/`c59c815`) and the ultra-resilient safenet suite exist only on branches (05 §7.3).
12. **Prior investigation** — stash@{0} contains a complete 2026-08-16 forensic report (10 phase docs); its conclusions align with this one.

---

## 9. Consolidated defect catalog (severity-ranked, evidence-backed)

### CRITICAL / HIGH

| # | Defect | Evidence | ✅/🔍 | Fix task |
|---|---|---|---|---|
| H-1 | **Subscribers lost on every `clean`/`reset`**: `_restore_bot_users` recreates `bot_users` without `approved` column (main.py:226-236), then INSERTs backup rows incl. `approved` → OperationalError caught+logged silently; all subscribers wiped | cli/main.py:226-236; bot/interactive.py:88 (F10, 02 §7.2) | ✅ Confirmed: word "approved" absent from CREATE TABLE DDL in main.py:226-236; `approved INTEGER NOT NULL DEFAULT 0` confirmed in interactive.py:88 | T1 |
| H-2 | **No approval workflow** ⇒ auto-delivery dead on fresh deploys; on-demand commands ungated | 02 §1.3, §7.1 | ✅ Confirmed: bot/ grep for "approve" returns only schema DDL + WHERE filters; no handler, no UPDATE SET approved=1 anywhere in src/ | T9 |
| H-3 | **Hardcoded decryption passwords/keys in source**: tut `b"fubvx788b46v"`, sks `b"dyv35224nossas!!"`, tmt `b"fubvx788B4mev"`, NetMod key `b"_netsyna_netmod_"`, SlipNet XOR key constants | crypto.py:128-130, 241 (03 §C1) | ✅ Confirmed: all 4 values read verbatim from live crypto.py at stated lines | T8 |
| H-4 | **`secure` tier silently builds zero records** (no verdict writer) | verdict_store.py:8 (01 §D4) | ✅ Confirmed: `upsert_record_verdict` defined at verdict_store.py:8 only; grep src/ returns exactly one match (definition) — zero callers | T10 |
| H-5 | **State DB never auto-pruned in production** (only caller is dead `_run_async_legacy`) | repo.py:714-781, orchestrator.py:678-688 (01 §D3) | 🔍 Inferred: `_run_async_legacy` is reachable from no entrypoint in the patched live path | T3 |
| H-6 | **CLI `prune` lacks orphan-hash guard** — can delete raw blobs still referenced by live records (the exact bug 5229d0b fixed for admin prune) | main.py:444-446 vs admin.py:171-176 (02 §7.4) | ✅ Confirmed: main.py:446 calls `prune_by_hashes(raw_hashes)` directly with no `get_all_known_hashes()` subtraction | T4 |
| H-7 | **Committed binaries** of a rejected module: 2×4.5 MB `.exe` in tree | git ls-files (F15, 04 §1) | ✅ Confirmed: `cmd/huntx-engine/` tracked .exe files | T19 |
| H-8 | **Inverted Go test coverage**: CI `go test -race ./...` exercises only the orphaned nested module (no real Go tests run); live release plane `internal/` + `cmd/huntx-tools` have zero `_test.go` files | 04 §2 | ✅ Confirmed: no `_test.go` in `internal/` or `cmd/huntx-tools/` | T18 |
| H-9 | **Production behavior defined by import-time monkey-patches** that diverge from shadowed class source; reading classes alone misdescribes production | F12, 01 §D2 | ✅ Confirmed: runtime_resilience.py:299-304 patches confirmed; class `_canonical_ingestion_sources` and patch version diverge semantically | T2 |
| H-10 | **5.2 GB git bloat**: 436 tracked runtime files (data_archive 410 files); 1.5 GB garbage tmp_packs; ~113 MB regenerated on main every 2h | F11, 05 §8 | 🔍 Inferred from dir sizes; git count-objects previously confirmed | T21/T22 |

### Concrete minimal fixes for the top 3 live-verified defects

**H-1 fix — add `approved` column to `_restore_bot_users` (cli/main.py:226-236)**

```python
# REPLACE existing CREATE TABLE block in _restore_bot_users():
cursor.execute("""
    CREATE TABLE IF NOT EXISTS bot_users (
        user_id TEXT PRIMARY KEY,
        chat_id TEXT NOT NULL,
        username TEXT,
        registered_at REAL NOT NULL,
        muted INTEGER DEFAULT 0,
        last_delivered_at REAL DEFAULT 0,
        default_format TEXT DEFAULT 'npvt',
        approved INTEGER NOT NULL DEFAULT 0    -- ← MISSING: causes OperationalError on restore
    )
""")
# Regression test to add: backup bot_users with approved rows → _cmd_clean → assert approved survives
```

**H-6 fix — port orphan-hash guard into `_cmd_prune` (cli/main.py:444-446)**

```python
# REPLACE (main.py:446):
#   raw_pruned = raw_store.prune_by_hashes(raw_hashes)
# WITH (mirrors admin.py:171-176 exactly):
live_hashes = set(repo.get_all_known_hashes())
orphan_hashes = [h for h in raw_hashes if h not in live_hashes]
raw_pruned = raw_store.prune_by_hashes(orphan_hashes)
skipped = len(raw_hashes) - len(orphan_hashes)
print(f"  - Raw store files deleted: {raw_pruned} ({skipped} skipped — still referenced by live records)")
```

**H-3 mitigation — externalize tut/sks/tmt passwords and NetMod key (crypto.py:127-131, 241)**

```python
# REPLACE hardcoded dict with env-backed version (keys are already env-backed if set,
# but fallback to plaintext — this makes the fallback auditable and removable):
_TUT_PASSWORDS: dict[str, bytes] = {
    ".tut": os.getenv("HUNTX_TUT_PASS_TUT", "").encode() or b"fubvx788b46v",   # ROTATE, then remove fallback
    ".sks": os.getenv("HUNTX_TUT_PASS_SKS", "").encode() or b"dyv35224nossas!!",
    ".tmt": os.getenv("HUNTX_TUT_PASS_TMT", "").encode() or b"fubvx788B4mev",
}
# NetMod (crypto.py:241): same pattern — HUNTX_NETMOD_KEY env with fallback b"_netsyna_netmod_"
# CI secret scan to add in validate job:
#   run: python -c "import subprocess; r=subprocess.run(['python','-m','rg','fubvx788|dyv35224|nossas|_netsyna_netmod_','src/'],capture_output=True); exit(0 if not r.stdout else 1)"
```



### MEDIUM
| # | Defect | Evidence |
|---|---|---|
| M-1 | `nm` routed in prod but `NmHandler.build` raises NotImplementedError (latent build-stage crash); `slipnet` same (unrouted) | nm.py:43-44, slipnet.py:184-185 (03 §C2) |
| M-2 | npvtsub skips URI validation that npvt applies (inconsistent strictness) | npvtsub.py:47-63 (03 §C3) |
| M-3 | npvt whole-payload b64 fallback decodes entire file first (unbounded memory) | npvt.py:99-105 (03 §C4) |
| M-4 | `/admin run` uses default `config.yaml` which doesn't exist (fails unless `HUNTX_CONFIG` set) | admin.py:142 (02 §7.3) |
| M-5 | Unthrottled expensive bot endpoints (`/count` JSON-extract GROUP BY = cheap DoS; also /status /formats /protocols /ping /setformat /mute /unmute /myinfo) | 02 §7.5 |
| M-6 | Unbounded per-request send volume (`/get`, `/latest` send every matching file) | 02 §7.6 |
| M-7 | O(users×files×size) re-hashing in delivery (hashes are content-global) | delivery.py:63/240 (02 §7.7) |
| M-8 | `_register_user` upsert wipes stored username (UPDATE sets username=NULL from non-/start callers) | interactive.py:123-126 (02 §7.8) |
| M-9 | Dual AWS credential paths (OIDC + static keys coexist) | huntx.yml:189-202,636-648 (04 §7.6) |
| M-10 | Gate workflows are non-enforcing (artifact-existence only), unpinned `actions/github-script@v9`, no timeout-minutes | 04 §3, §7.5 |
| M-11 | Cron overlap: 2h cadence vs 115m+25m jobs, cancel-in-progress false → queueing | 04 §7.4 |
| M-12 | Two outputs writers with conflicting naming/retention (export deletes build's derivative copies after 3 days) | 01 §D6 |
| M-13 | Inconsistent run defaults (timeout 9000/12600/16200; workers bounded vs unbounded; two partial-success knobs) | 02 §7.13 |
| M-14 | Stale policy doc (CONVERGENCE "never commit to main") vs sanctioned mirror | 04 §7.8 |
| M-15 | Exception text leaked to admin chat | admin.py:119,196 (02 §7.10) |

### LOW / INFO
L-1 `_respond_myinfo` labels local time UTC (handlers.py:308) · L-2 `/latest 0` accepted (no lower bound) · L-3 `_set_user_pref` UPDATE-only no-op for non-/start users · L-4 `muted = total - active` misleading stat (interactive.py:147) · L-5 WAL set twice · L-6 ingest progress-log condition rarely fires · L-7 `get_records_for_build` silent-empty when `from_sources` empty · L-8 slipnet hashes encrypted link vs npvt hashes stripped plaintext (undocumented identity-semantics split) · L-9 fragile decrypt heuristics (`"." in text and len>50`) · L-10 v2ray_collector fake 100 ms latency + runtime `go run` module download · L-11 `docs/catalog.json` stale committed copy · L-12 cpython-314 `__pycache__` alongside 311 · L-13 pr-validation push trigger misses direct main pushes · L-14 raw `int()` env parsing in delivery/_cmd_bot vs fail-soft policy · L-15 handlers.py unconditional Telethon import defeats optional-import pattern · L-16 `build_result["generation"]` never set (fallback always used) · L-17 huntx-engine latent defects (unbounded b64 accumulator, no-op heal, batch ctx, TLD drift) — moot if archived.

---

## 10. Phase 9 — Implementation roadmap

Dependency graph: **T1–T8 (wave 1) are independent · T2 precedes T3/T5/T6/T7 · T10 decision precedes T11 · T18–T22 (hygiene) parallel-safe.**

### Wave 1 — Stabilize (verified defects, small diffs) — ~2–3 days
- **T1** Fix `_restore_bot_users`: recreate with full current schema incl. `approved` (or `CREATE TABLE AS SELECT` backup/restore). Add regression test simulating clean→restore→approved-survives. *cli/main.py:226-236.*
- **T4** Port admin prune's orphan-hash guard (`candidate_hashes - get_all_known_hashes()`) into `_cmd_prune`. *main.py:444-446.*
- **T8** Externalize tut/sks/tmt passwords, SlipNet key constants, NetMod key to env with current values as documented fallback **only after rotation decision**; add secret-scan CI step. *crypto.py:106-131,241.*
- **T9-min** Interim: document the manual-SQL approval procedure as a runbook (`docs/runbooks/bot_approval.md`) — unblocks operators immediately.
- **T12** Fix M-4: `/admin run` default config → `configs/config.prod.yaml` (or fail with explicit message). *admin.py:142.*
- **T13** Add cooldowns to the 8 unthrottled bot commands; cap per-request file count for `/get`/`/latest`. *handlers.py, delivery.py.*
- **T14** Guard `nm` route: either implement `NmHandler.build` (ZIP like siblings) or remove `nm` from the prod route until build exists. Same decision for `slipnet`. *nm.py:43-44.*
- **T15** Stop username wipe: `_register_user` UPDATE `username = COALESCE(?, username)`. *interactive.py:123-126.*

### Wave 2 — Inline the patch layer (the structural keystone) — ~3–5 days
- **T2** For each of the 6 installers: move patch semantics into the class, delete the shadowed method, convert installer to a no-op shim for one release, then delete. Order by blast radius: `repo_hardening` → `migration_safety` → `consumer_reconciliation` → `transform_contract` → `dev_manifest_contract` → `runtime_resilience` (largest). Each step must keep the 498-test suite green; add a "no patch installers imported" lint test at the end. *F12 list.*
- **T3** After T2: move `repo.prune_old_data(HUNTX_PRUNE_DAYS)` into the hardened cleanup stage; delete `_run_async_legacy`. *hardened_orchestrator.py:309-319, orchestrator.py:470-719.*

### Wave 3 — Wire-or-excise dormant features (product decisions) — ~1 week
- **T10** Decision: complete the verdict pipeline (A2+A3: syntax verdicts at transform, probe verdicts via latency_benchmarker, `secure` tier becomes real) **or** excise `secure` from the config surface + delete `record_verdicts` machinery. Same meeting decides lifecycle trust (A4: write events from ingest outcomes, or drop `source_lifecycle`).
- **T9** Build the approval workflow: `/approve <id>` `/deny <id>` `/list pending` (admin-gated, numeric IDs), persisting `approved` + `approval_evidence`; update README "deny-by-default" claim to match. *bot/admin.py.*
- **T11** Wire `StreamingChunkParser` into npvt/npvtsub large-file path (fixes M-3); retire whole-payload fallback. *formats/streaming.py → npvt.py:99-105.*
- **T5/T6/T7** Merge transform loops; unify run commands (keep hardened defaults: 12600s, bounded workers 1..64, single partial-success knob); single `outputs/` writer with one naming scheme. *01 §D6/D7/D8.*
- **T16** Collapse orchestrators to one class; delete `UnifiedOrchestrator` or keep as the wired integration shell per T10 outcome; delete `cli/commands/run.py`, publish hash-cache remnants, `RejectsStore` (or wire it). *01 §2, §D9.*
- **T17** Add signal handling (SIGTERM → graceful stage cancel + lock release) to CLI. *02 §3.7.*

### Wave 4 — Test & release-plane hardening — ~3–4 days
- **T18** Write native Go tests for `internal/{outputverify,releasemanifest,runtimegen,sitegen}` (port cases from `tests/test_runtime_generation.py` + `test_release_governance.py`); fix CI so `go test ./...` covers the root module's real packages. Optionally delete the orphaned engine module first (T19) so the wildcard is clean.
- **T19** Archive `cmd/huntx-engine/` (tag `archive/huntx-engine`), remove both `.exe` from the tree, add `*.exe` to `.gitignore`. Update ledger to record the removal.
- **T23** Pin `actions/github-script@v9` by SHA in both gates; give gates real enforcement (download + validate `run-summary.json` metrics) or delete them; add `timeout-minutes`.
- **T24** Remove static AWS keys from restore/persist once OIDC is confirmed sole path (M-9).
- **T25** Fix stale perf test (fixture rows lack `id` → KeyError transform.py:61) or delete `tests/perf` marker content; re-run flaky `test_session_lease` heartbeat with monotonic timing (F8).

### Wave 5 — Repo hygiene & documentation — parallel, low risk
- **T20** Untrack `data_archive/` (410 files, 811 MB) + `outputs*` large generated files via `.gitignore` + `git rm --cached`; move archive to external storage. **Non-destructive** (files stay on disk; history keeps old copies). Full history rewrite (filter-repo of state-branch blobs) is a separate **destructive** maintainer decision (§12).
- **T21** Adopt LFS or artifact-only publication for the 12 mirrored paths, or reduce mirror cadence; document the growth policy (04 §7.7).
- **T22** Delete the 31 merged-lingering branches (05 §3.1) after confirming donor SHAs kept; salvage first: cherry-pick/re-test `38e791f`+`c59c815` (A7) and review `codex/ultra-resilient-partial-workflows` (A8).
- **T26** Docs: refresh README (85 sources, 5 commands, 16 formats); write the missing docs — secret provisioning checklist, DR runbook, env-var reference table (~30 knobs), bot deployment model; move `full_audit_report.md` → `docs/history/`; mark CONVERGENCE invariant #46 as superseded; retire `docs/catalog.json` stale copy.
- **T27** Local hygiene: rotate + delete `temp_bot_init/` & `temp_data_interactive/` session files after session rotation (F16); drop stash@{1} binaries; decide on stash@{0} prior-report preservation.

### Validation plan
Every wave gates on: `pytest -m "not perf" --strict-config --strict-markers` (498 baseline) · `flake8` + `mypy` · `go test ./...` (post-T18) · workflow contract tests (`test_workflow_resilience.py`) · one full cron cycle observed end-to-end (run → verify → checkpoint → persist → publish → mirror) before and after each wave. Wave 2 additionally requires a diff of `run-summary.json` envelopes across 3 consecutive runs pre/post patch-inlining.

### Rollback plan
Waves 1/4/5 are independent commits — revert per-commit. Wave 2 keeps installer shims for one release (T2), so rollback = re-enable installer. Wave 3 decisions (T10) are config-surface changes behind the existing `publication_tier` field — excision is reversible by re-adding the tier. State-DB migrations are forward-only by design (v1–v10 pattern); any schema change in T10 must ship with a postcondition-checked migration and a `persist/` snapshot taken by CI `restore` before the first post-change run.

---

## 11. Blockers & caveats of this investigation

1. **No Go toolchain locally** (network-blocked environment) — Go analysis is static; Go tests were not executed here (CI runs them). The 2 pytest failures (`test_v2ray_collector_connector`) need `go` on PATH and pass in CI (F8).
2. **Local main was 1 commit behind origin** (`473d8f9`, one automated output commit) — no code delta.
3. **Credential files on disk were not read** (`temp_*/bot.session`) — presence verified, content untouched (F16).
4. **`.project_config.toml` / vault files** never read per policy.
5. **Prior forensic report in stash@{0}** noted but not extracted (it is a GitHub-Desktop stash of someone else's session; its conclusions reportedly align).
6. Shell environment quirk (broken `$VAR` expansion in the investigation shell) — all commands used literal paths; no impact on findings.

## 12. Decisions requiring the maintainer (destructive / policy)

- **History rewrite** (`git filter-repo`) to purge 24× 43–51 MB `state.db` blobs on `huntx-state`/`mergebot-state` + 1.5 GB garbage tmp_packs: destructive, requires force-push coordination. Recommended after T20/T22.
- **Secret rotation** for the hardcoded decoder passwords (T8) if they are third-party secrets.
- **`TELEGRAM_USER_SESSION` rotation** before deleting temp session files (T27).
- **Donor-branch deletion** only after the ledger is retired or its SHA citations are archived.
- **Confirmation of the consolidation target** assumed in this report (§0 flag).

---

## Appendix A — Evidence ledger (verified facts F1–F20)

F1 repo/main/HEAD `8ffd830` (automated) · F2 pyproject huntx 0.2.0, py≥3.11, entry `huntx.cli.hardened_main:main` · F3 root go.mod stub; engine has own go.mod (`go 1.26`, unbuildable by CI's 1.23) · F4→F6 LOC census (15,003 src / 10,306 tests / 1,612 scripts / 2,087+ Go; "754 .go files" = 737 module-cache + 17 project) · F7 dir sizes (data_archive 811M, .tmp 139M, outputs_dev 130M, data 51M) · F8 test health: 498 passed / 2 env-dependent failed / 57 subtests / 91s; stale perf test KeyError (fixture rows lack `id` field); flaky session-lease heartbeat · F9 config.prod.yaml 85 sources, 1 route → 12 formats → chat 8526064109; env contract TELEGRAM_API_ID/API_HASH/USER_SESSION (+PUBLISH_BOT_TOKEN/TELEGRAM_TOKEN) · F10 ✅ H-1 verified: `_restore_bot_users` at main.py:226-236 — the word "approved" does NOT appear anywhere in the CREATE TABLE DDL; interactive.py:88 confirms the authoritative schema has `approved INTEGER NOT NULL DEFAULT 0`; any backup row including `approved` will produce OperationalError on INSERT · F11 git hygiene: .git 5.2 GB, 436 tracked runtime files, largest tracked outputs_dev/proxies.json 32 MB · F12 six monkey-patch installers enumerated and confirmed: runtime_resilience, transform_contract, dev_manifest_contract, migration_safety, repo_hardening, consumer_reconciliation + telegram hardening · F13 hidden analysis caches 427 MB untracked · F14 16 registered format handlers vs 12 routed; 19 URI schemes · F15 2 committed .exe in `cmd/huntx-engine/`; 53 branches; stale docs/catalog.json; 12 mirror paths; README 49-vs-85 stale · F16 temp session files untracked, never committed; data/ = logs only; no tracked secrets in git index.

**New live-verified facts (added post-grep-confirmation):**

F17 ✅ `upsert_record_verdict` — grep `src/` returns exactly **one** match at `verdict_store.py:8` (the function definition). Zero callers exist anywhere in `src/`. The `secure` publication tier is structurally impossible to populate.

F18 ✅ Hardcoded credentials at **exact lines**: crypto.py:128 `b"fubvx788b46v"` (TUT), :129 `b"dyv35224nossas!!"` (SKS), :130 `b"fubvx788B4mev"` (TMT); crypto.py:241 `b"_netsyna_netmod_"` (NetMod ECB key). All four read verbatim from the live source file. The env-override path exists at the same lines but falls back to these literals when the env vars are unset.

F19 ✅ CLI `prune` orphan-guard absence — main.py:446 reads verbatim: `raw_pruned = raw_store.prune_by_hashes(raw_hashes)`. The variable `raw_hashes` is populated directly from `res.get("raw_hashes", [])` at main.py:436, which is the full set of age-eligible raw hashes from `prune_old_data` — **not** the subset of hashes unreferenced by live records. The equivalent admin prune guard is at admin.py:171-176 and correctly subtracts `get_all_known_hashes()`.

F20 ✅ No approval handler — grep `D:/github/huntx/src/huntx/bot/` for `approve` returns exactly: `interactive.py:88` (schema DDL column), `interactive.py:95` (migration ADD COLUMN), `interactive.py:96` (ALTER TABLE statement), `interactive.py:138` (WHERE filter on SELECT), `interactive.py:144` (WHERE filter on COUNT). No file in `src/huntx/bot/` contains an `/approve` command handler, nor any statement that sets `approved = 1` from user input.

## Appendix B — Report index

| File | Scope | Lines (after enrichment) |
|---|---|---|
| `01_pipeline_core.md` | core/, pipeline/, state/, store/ — call chains, orchestrator lineage, schema, defects D1–D10 | 137 |
| `02_bot_cli_config.md` | bot/, cli/, config/, utils/ — command surface, auth model, delivery, CLI, config schema, 18 defects | 265 |
| `03_formats_connectors_publishers.md` | formats/ (16+3+1), connectors/ (4), publishers/ — catalog, crypto stacks, defects C1–C8, domain knowledge | 113 |
| `04_go_ci_scripts.md` | Go modules, CI job graph, publication story, scripts/, systemd, 13 defects, Go-vs-Python duplication matrix | 235 |
| `05_git_archaeology_hidden.md` | 909 commits, 7 eras, 50-branch census, hidden-feature register H1–H22, conductor tracks, unmerged fixes | 228 |
| `06_docs_knowledge.md` | docs/ freshness, prior-audit status, README claims-vs-reality, knowledge register, contradictions register | 121 |

*End of consolidated report.*

