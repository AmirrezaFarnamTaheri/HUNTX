# Subagent F — Documentation & Institutional Knowledge Report

Scope: `docs/`, `conductor/`, `full_audit_report.md`, `README.md`, `graphify-out/`, prior-analysis caches · Written by the lead agent after subagent F suffered repeated connection aborts; all citations verified.

**Live-verification status:** ✅ = confirmed by reading exact file; 🔍 = derived/inferred.

---


## 1. Knowledge artifact inventory

| Path | Lines | Content | Freshness vs code |
|---|---|---|---|
| `docs/history/MASTER_FORENSIC_COMPENDIUM.md` | 165 | Jul-25 "9-phase forensic audit" that BUILT UnifiedOrchestrator | **STALE + INACCURATE** (see §2) |
| `docs/history/HARDENING_AUDIT_2026-07-12.md` | 173 | Hardening-era audit feeding PRs #43–#56 | Historical (superseded by convergence) |
| `docs/history/AUDIT_2026-07-26.md` | 384 | Six-repo comparative audit → closure ledger input | Historical |
| `docs/history/HUNTX_AUDIT_CLOSURE.md` | 74 | D-01…D-25 + SYN-01…12 disposition ledger | **Partially stale** (D-11 "no commits to main" overturned by PR #75) |
| `docs/history/CONVERGENCE_2026-07-27.md` | 97 | PR #61 convergence: issues #44–#47, PRs #58–#60 | Authoritative for its era; one invariant stale (outputs-on-main) |
| `full_audit_report.md` (root) | 384 | June deep technical audit, F-01…F-28 | **Mostly remediated**; F-04 keys partially remain (see §2) |
| `docs/DONOR_PR_ABSORPTION_LEDGER.md` | 219 | Per-value-unit absorption decisions for donor PRs #58/#59/#60 | Authoritative governance record |
| `docs/GENERATED_OUTPUTS_MODEL.md` | 62 | Current publication model (generated-outputs branch + main mirror) | **CURRENT AUTHORITY** (supersedes convergence on this topic) |
| `docs/RUN_HEALTH.md` | 156 | success/degraded/fatal contract, safenet, diagnostics | Accurate (matches run_health.py + report_runtime_health.py) |
| `docs/PERSISTENT_LIFO_INGESTION.md` | 108 | LIFO window/lease/residue contract | Accurate (matches ingestion_queue.py) |
| `docs/PUBLISHING_MODES.md` | 82 | post_on_change/telegram modes | Accurate |
| `docs/USER_GUIDE.md` | 326 | Config, formats, protocols, CLI, bot, session setup | Mostly accurate; misses `prune`, approval workflow gap |
| `docs/DEVELOPMENT.md` | 141 | Structure, setup, how-to-add-X recipes | Accurate; good onboarding |
| `docs/plans/2026-07-25-next-gen-architecture-plan.md` | 182 | Next-gen plan (streaming/geo/healing) | Executed-but-dormant (components merged, unwired) |
| `docs/superpowers/plans/2026-07-25-end-to-end-resilience-performance.md` | 240 | Resilience/perf plan | Partially executed (latency gate unwired) |
| `docs/solutions/lessons-learned.md` | 17 | 3 operational lessons (conflict markers, LSP, Windows basetemp) | Accurate lore |
| `docs/handoffs/ce_handoff_huntx_optimization.md` | 51 | 12-task optimization handoff (mypy/flake8 zero, lru_cache, b64 DRY) | Accurate; explains perf investments |
| `docs/index.html` + `docs/assets/js/*` | — | GatherX Pages SPA (Preact/Tailwind) reading catalog.json | LIVE (deployed by CI) |
| `docs/catalog.json` | — | **STALE** (2026-02-16, old schema, 5 files) — CI regenerates per run | Stale committed copy |
| `conductor/` (index, product, tech-stack, workflow, styleguides, 2 tracks) | ~130 | Agent-orchestration context + track specs | Tracks "complete"; track-1 runtime-dormant |
| `README.md` | ~230 | Product overview | **Stale claims**: "49+ sources" (actual 85), "4 CLI commands" (actual 5), "12 formats" (registry 16) |
| `graphify-out/` | 660 KB | graph.json + cache only — **no GRAPH_REPORT.md exists** | n/a (raw graph, no human summary) |
| `.codegraph/ .serena/ .cocoindex_code/ .code-review-graph/ .smart-coding-cache/` | 427 MB total | Tool indexes, no human findings | Untracked caches |

## 2. Prior-audit distillation & current status

**`full_audit_report.md` (June, F-01…F-28)** — the four systemic risks it named and where they stand now:
- **F-01/F-02 (P0) output-path drift** (CI committed stale repo-root outputs; orchestrator wrote persist/data): **REMEDIATED** — the entire generated-outputs control plane (PRs #66–#70, #75) + `sync_generated_outputs_to_main.py` exists precisely to fix this; verified live (outputs commit every 2h).
- **F-02 (P0) shared MTProto session → AUTH_KEY_DUPLICATED**: **REMEDIATED by design** — per-session lock tables (report C §4), session-lease file locks, single-session serialization accepted as the trade; issue #44 tests pin it.
- **F-04 (P1) embedded third-party keys**: **PARTIALLY REMEDIATED** — HAPP RSA keys moved to env/`persist/keys` (commit `32f1036`), but `.tut/.sks/.tmt` fallback passwords, SlipNet XOR constants, and NetMod key **remain hardcoded** (crypto.py:106-131,241; report C C1). The June report called this "IP/DMCA exposure" — still open.
- **F-09 409 bot-token conflict**: **REMEDIATED** — fail-closed shared-token gate (interactive.py:51-57; report B §5.1).
- Timeout inversion (orchestrator > job timeout): **REMEDIATED** — layered watchdog now internal 5400s < TERM 105m < kill 115m < cron 120m (report D §9.1).

**`MASTER_FORENSIC_COMPENDIUM.md` (Jul 25) — reliability warning.** This document is itself an artifact of the next-gen track session, and contains claims contradicted by the code: lists decoders `v2ray, clash` that **do not exist** in `formats/` (actual: 16 handlers, report C §2); claims "Latency Benchmarker integrated into core pipeline" (it has **no production caller**, report E H3); claims UnifiedOrchestrator "incorporating all optimization and hardening" (it **skips ingestion/export**, report A D1); schema description (`verdicts`, `delivery_log` tables) doesn't match schema.sql (actual: `record_verdicts`, `publication_deliveries`). **Treat as marketing-grade, not forensic-grade** — its creation was the track's deliverable, and the convergence era (2 days later) had to re-derive everything.

**`HUNTX_AUDIT_CLOSURE.md`** — the most honest ledger: 25 comparative findings mapped with status vocabulary; notable **still-Open items**: D-02 SIP002 plaintext credential fixtures, D-05 Hysteria2 obfs aliasing fixtures, D-07 TLS-verification-bypass policy at build, D-12 "NPVT URI extraction remains lexical" (protocol-aware validation wanted), SYN-01 typed proxy IR, SYN-06 native client gates, SYN-08 observability contract. These are the **pre-existing, self-acknowledged gap list** — the consolidation roadmap should inherit them.

**`DONOR_PR_ABSORPTION_LEDGER.md`** — per-unit dispositions (Adopted / Adopted-and-extended / Rejected-with-guardrail) with target evidence for PR #59's defensive audit (env fail-loud, atomic UTF-8, prune blob-safety, download caps, zip bounds…) and PR #58's rejected items (divergent Go runtime, fail-open governance, mutable telemetry, no-op healing). **Key governance fact:** `cmd/huntx-engine` is explicitly "Rejected with negative guardrail" here (ledger:141) — yet the code + 2 .exe binaries remain in-tree (report D #1).

## 3. docs/solutions & plans distillation

- **lessons-learned.md**: (1) post-stash conflict-marker sweep `rg "<<<<<<<|>>>>>>>|=======" src/ cmd/ tests/` before running; (2) LSP-invariant signatures — parents must declare the keyword args subclasses add (`process_pending(*, deadline, max_batches)`); (3) Windows pytest `--basetemp` isolation for background runs. All three explain visible code/CI choices.
- **next-gen plan**: 4 deliverables (StreamingChunkParser <50MB RAM, GeoRoutingEngine taxonomy, SelfHealingDaemon backoff 5m→6h, UnifiedOrchestrator integration) — all exist + tested, none wired (report E §5).
- **resilience-performance plan**: latency gate >3000ms filter, decoder edge-case tests, bot freshness alerts — decoder tests ✅, alerts exist but **dead** (report B §1.8), latency gate unwired.
- **ce_handoff**: explains the `lru_cache(8192)` on normalize_text/hash_string, 64KB buffered RawStore reads, tests/perf/ suite, b64.py DRY — the perf-investment provenance.

## 4. README claims-vs-reality

| README claim | Reality | Verdict |
|---|---|---|
| "49+ Telegram channels" | 85 sources (config.prod.yaml, constants.py:10) | **Stale** (undercount) |
| "12 formats" | 16 registered handlers; 12 in prod route; +3 derivatives | Undercount/ambiguous |
| "20+ protocols" | 19 URI schemes (router.py:6-26) | ~Accurate |
| "4 CLI commands" | 5 (`run, bot, clean, reset, prune`) | Stale (prune undocumented) |
| "Quality Gates — linting, typing, tests" | True: flake8+mypy+pytest in CI, strict markers | Accurate |
| "Auto-Deploy Pages frontend" | True (deploy-pages job) | Accurate |
| "deny-by-default bot access" | Delivery gate yes; **but no approval workflow exists** (report B §7.1) and on-demand commands ungated | **Misleading** |
| "Resumable publication" | True (publication ledger + bot delivery checkpoints) | Accurate |
| "Factory reset CLI + CI trigger" | True (reset subcommand + workflow_dispatch reset w/ confirmation string) | Accurate |
| "Zero-budget CI, 2h cron" | True | Accurate |

## 5. graphify-out harvest

Only `graph.json` + `cache/` — **no GRAPH_REPORT.md or summary exists** (checked). The 660 KB graph is raw machine data from a prior graphify run; no human-readable findings to preserve. (The earlier plan assumption of a GRAPH_REPORT was wrong.)

## 6. Conductor track register

| Track | Status file says | Actual outcome |
|---|---|---|
| `next_gen_architecture_20260725` | complete (`a2736a8`) | Code merged via PRs #72/#75 but **runtime-dormant**; plan checkboxes unchecked; produced the Compendium (see §2 reliability warning) + 2 committed .exe binaries |
| `resilience_monitoring_20260725` | completed (metadata.json) | Decoder tests + freshness alerts landed; latency gate unwired |

`conductor/` also holds product.md/tech-stack.md/workflow.md/code_styleguides (python.md, go.md) — agent context docs, unremarkable but the styleguides document the mypy/flake8/120-col conventions.

## 7. Institutional knowledge register (must survive migration)

1. **Layered watchdog & degraded-success semantics** (RUN_HEALTH.md + huntx.yml + report_runtime_health.py): internal budget < TERM < kill < job < cron; exit 124/137/143 + good checkpoint = degraded, not fatal.
2. **Immutable generation protocol** (GENERATED_OUTPUTS_MODEL.md + runtimegen): payload→manifest→cmp→pointer-last; reset backs up pointer first; `RESET-HUNTX-STATE` literal confirmation.
3. **Legacy cumulative bootstrap** (GENERATED_OUTPUTS_MODEL.md §"Legacy cumulative bootstrap"): rendered `proxies.txt/.json/_b64sub` history is authoritative migration input; sentinel ts=0; unrecoverable-non-empty fails closed; earliest-first merge.
4. **vmess canonical identity** (npvt.py:29-43 + DB v10 migration + outputs_dev manifest): three subsystems share one remark-stripped sorted-key canonicalization — change it and you re-key the dedup universe.
5. **Decoder provenance & crypto parameters** (report C §10): Slipstream schemas V1–V28, HAPP 3-key generations, TUT PBKDF2-1000-iterations matching pycryptodome, NetMod ECB key, XXTEA custom-delta port — none documented anywhere except code comments.
6. **Why patches, not refactors** (report E §7.1): hardening wave shipped invariants against a frozen orchestrator hierarchy mid-production; the patches ARE the contract until inlined.
7. **Donor governance** (DONOR_PR_ABSORPTION_LEDGER.md): frozen donor SHAs `dc3d795`/`443d169` are cited evidence; deleting those branches breaks the ledger.
8. **Anti-fake CI gates** (report E H7): the project defends against its own CI faking runs via runtime-diagnostics marker verification — unusual, deliberate.
9. **Session bootstrap procedure** (USER_GUIDE.md §"Telegram User Session" + make_telethon_session.py): StringSession creation → `TELEGRAM_USER_SESSION` secret → per-session lock identity. The only path to rotate the MTProto identity.
10. **Windows ops lore** (lessons-learned #3, .flake8 note in pyproject): pytest basetemp isolation; flake8 config lives ONLY in `.flake8` (pyproject says so explicitly).
11. **Approval is manual SQL** (README:113 + report B §1.3): "Administrator approves the user in the bot-user database" — no code path; operational knowledge that will be lost if the bot is redeployed elsewhere.
12. **Repo founding provenance** (report E §2 era 0): ROADMAP.txt containing the AI's refusal text; GATHEREX + smgo/compare sibling-repo merges — the codebase is a 3-repo consolidation already.

## 8. Documentation gaps (undocumented but required)

1. **User approval workflow** — the single biggest operational gap (gate exists, procedure doesn't; not even a runbook).
2. **Secret provisioning inventory** — TELEGRAM_API_ID/API_HASH/USER_SESSION, PUBLISH_BOT_TOKEN/TELEGRAM_TOKEN, HUNTX_ADMINS, HAPP PEMs, AWS (OIDC+static) — scattered across workflows/README/USER_GUIDE; no single checklist.
3. **Disaster recovery** — S3 generation restore is tested, but "lose everything, rebuild from git" is not documented (session re-bootstrap, approval re-grant).
4. **Go build/run** — huntx-tools build is CI-only; no local-dev Go doc; huntx-engine's `go 1.26` makes it unbuildable (report D #3).
5. **`huntx prune`** — exists, undocumented in README/USER_GUIDE.
6. **Env-var reference** — ~30 HUNTX_* knobs exist (reports A §7, B §6); no consolidated table anywhere.
7. **Data lifecycle** — data_archive 811 MB tracked with no retention doc; outputs_dev unbounded growth acknowledged but no policy.
8. **Bot deployment model** — systemd/mergebot.service is stale pre-rename; the actual model (CI cron + manual `huntx bot`) is nowhere stated as a whole.

## 9. Contradictions register

| # | Contradiction | Parties |
|---|---|---|
| 1 | "Generated output is never committed to main" vs sanctioned 2-hourly main mirror | CONVERGENCE_2026-07-27.md vs GENERATED_OUTPUTS_MODEL.md + HUNTX_AUDIT_CLOSURE D-11 (stale) |
| 2 | Compendium's decoder list (`v2ray`, `clash`) & "benchmarker integrated" vs actual code | MASTER_FORENSIC_COMPENDIUM.md vs formats/ + latency_benchmarker callers |
| 3 | README "49+ sources / 4 commands" vs 85 sources / 5 commands | README.md vs config.prod.yaml + cli --help |
| 4 | Ledger "huntx-engine rejected" vs engine + 2 .exe still in-tree | DONOR_PR_ABSORPTION_LEDGER.md:141 vs cmd/huntx-engine/ |
| 5 | README "deny-by-default bot access" vs ungated on-demand commands + no approval workflow | README.md vs bot/handlers.py |
| 6 | June audit F-04 "embedded keys" marked fixed (HAPP→env) while tut/sks/tmt/netmod/slipnet keys remain | full_audit_report.md vs crypto.py:106-131,241 |
| 7 | Compendium schema (`verdicts`, `delivery_log`) vs real schema (`record_verdicts`, `publication_deliveries`) | MASTER_FORENSIC_COMPENDIUM.md vs state/schema.sql |
