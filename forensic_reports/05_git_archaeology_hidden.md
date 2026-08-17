# E — Git Archaeology & Hidden-Capability Report (HUNTX)

**Subagent:** E (git archaeology / hidden capabilities) · **Date:** 2026-08-17 · **Repo:** `D:/GitHub/HUNTX` (`github.com/AmirrezaFarnamTaheri/HUNTX`)
**Method:** read-only git forensics (`git log/shortlog/for-each-ref/merge-base/ls-files/show/stash`), working-tree sweep. Local `main` = `8ffd830` (origin/main was 1 commit ahead: `473d8f9`, run 31970163001).

**Live-verification status:** ✅ = confirmed by reading git output or source; 🔍 = derived/inferred from git history; ⚠️ = stale-risk (based on commit messages; code may have changed).

---


## 1. Repository vitals

| Metric | Value |
|---|---|
| Total commits on main | **909** |
| First commit | `1a2a738` 2026-02-05 23:43 +0330 "Initial commit" (only `.gitattributes` + `ROADMAP.txt`, 5883 lines) |
| Last commit (local main) | `8ffd830` 2026-08-16 18:30 UTC "Update HUNTX outputs from run 31964506908/1" |
| Lifespan | 6 months 11 days |
| Merge commits | 61 (PRs #1–#75, several numbers skipped) |
| Tracked files | 719 |
| Branches | 50 (3 local non-main + main + 46 remote non-main + origin/main) |
| Tags | none · Stashes: 2 (see §4) |
| Object store | **2.55 GiB pack + 1.04 GiB loose + 1.50 GiB garbage** (two orphaned `tmp_pack_*` files from interrupted fetch/gc) |

**Monthly cadence (all refs reachable from main):** Feb 193 · Mar 86 · Apr 71 · May 31 · Jun 19 · **Jul 318** · **Aug 191**. Bimodal: Feb sprint + Jul/Aug convergence+next-gen surges; Mar–May are almost entirely bot output commits.

**Authors (all 909 main commits):**

| Author | Commits | Identity |
|---|---|---|
| Farnam `<taheri.farnam@gmail.com>` | 305 | Human owner (local/agent-supervised commits, +0330) |
| huntx-bot | 254 | CI bot — legacy "Update outputs [skip ci]" era |
| github-actions[bot] | 177 | CI bot — current "Update HUNTX outputs from run …" era |
| Farnam Taheri | 108 | Human owner (early identity, merges via web UI) |
| AmirrezaFarnamTaheri | 57 | Human owner (GitHub web/agent-generated, Feb sprint) |
| google-labs-jules[bot] | 3 | Jules agent (audit fixes, mypy fixes — Jun) |
| Antigravity AI | 2 | Google Antigravity agent (v2ray_collector port, Jun 11) |
| coderabbitai[bot] | 1 | CodeRabbit auto-fixes (`86f5754`, Jul 14) |
| dependabot[bot] | 1 | Actions deps bump (`10c3e15`, Jul 14) |
| mergebot-bot | 1 | CI bot — first output commit of the legacy era |

**Human vs bot:** ~470 human (52%) / ~439 bot+agent (48%). The human is one person (Farnam Taheri, 3 name variants = 470 commits); everything else is CI or AI agents (Jules, Claude, Codex, Antigravity, v0agent, CodeRabbit). Branch-only authors not on main: **Claude** (12 commits, PR #59 donor branch), **v0agent** (1, deep-technical-audit).

---

## 2. Era timeline

| # | Era | Dates | Evidence (commits) |
|---|---|---|---|
| 0 | **Origin: AI-roadmapped MergeBot** | 2026-02-05 | `1a2a738` Initial commit = only `ROADMAP.txt` — an AI-generated pipeline roadmap that *opens with the model's refusal text* ("I can't help design … a system … used for evasion/abuse … What I can do is …"), then a phased ETL plan. Implementation begins same day: `09536ce` "Implement MergeBot application structure" |
| 1 | **MergeBot sprint (PRs #1–#27)** | 2026-02-05 → 02-09 | PR #1 `20be445` mergebot-impl; PR #3 roadmap completion `20b294a`; Jules branches `e5b0c94`/`6052d7f`; Telegram fixes #9–#14; 92% test coverage claim `1ca6aa9`; Telethon user sessions `0b8e321` |
| 2 | **GatherX identity + frontend (PRs #28–#37)** | 2026-02-09 → 02-21 | `58f6949` "LTS1.0" (outputs/ + outputs_dev/ born, mergebot-output/ deleted); **GATHEREX sibling repo merged twice** `3de15d8`/`49ca944` (2026-02-10, +162k lines of outputs); **`48afeae` "REBRAND Backend to HuntX"** (src/mergebot→src/huntx rename); frontend `b17680c` (Feb 16); workers/timeout PR #37 `1ea079c` |
| 3 | **Autonomous cruise (bot-only era)** | 2026-02-21 → 06-10 | ~250 "Update outputs [skip ci]" commits by huntx-bot; only human work: `75eddc3` "Create HuntX_Master_Audit_Report.md" (Apr 29, later deleted in `7004d29`), `7004d29` db-indexing/bot-elevation (May 22, last skip-ci commit `f448638` May 21) |
| 4 | **Integration + first audit** | 2026-06-11 → 06-18 | `fec2777`/`686b02b` port of **smgo** Telegram collector → `v2ray_collector` (Antigravity AI); `52c9c98` "Merge branch 'compare/main' … (Integrate v2ray_collector)" — a **third sibling repo**; `9008089` session locking ported "from duplicate repository"; audit wave: v0agent report, `99c59ab` remediation, `32f1036` **F-04: HAPP keys → env vars**, zip-slip/zip-bomb fixes `c7459c7`; Jules PR #41 `e90817c`; mypy PR #42 `fb278b5`; `full_audit_report.md` committed |
| 5 | **Hardening era (PRs #43–#56)** | 2026-07-12 → 07-16 | PR #43 `28ab3f5` end-to-end-hardening-20260712 (issues #44–#47 root fixes); PR #49 `4814405` synthesis hardening; **orchestrator generations born:** `bb910cd` HardenedOrchestrator + resilience/scoring engines (Jul 12), `189025a` OptimizedHardenedOrchestrator (Jul 14), `d8ec8e5` hardened_main entry point, `623f886` GovernedBuildPipeline, `c405167` runtime_resilience monkey-patches (Jul 16); agent perf tracks PRs #51/#53/#54/#55/#56 (LIFO ingestion `75ebb3b`); CodeRabbit + dependabot merges |
| 6 | **Conductor + convergence era (PRs #58–#70)** | 2026-07-25 → 07-30 | `f23eb8a` conductor init; `07e2365` **UnifiedOrchestrator + Master Forensic Compendium**; `6ae19a9` AsyncCircuitBreaker/ProxyScoringEngine; `4d91077` remove tracked temp_state.db; `6990bc4` temp_* gitignore hygiene; donor branches frozen (PR #58 = `dc3d795`, PR #59 = `443d169`); **PR #61 `6ac5ef7` convergence** (issues #44–#47 closed, PRs #58/#59/#60 consolidated); PRs #62/#64/#65 ultra-resilient production runs; PRs #66–#70 generated-outputs publisher control plane (`4d4447b` workflow born Jul 29); anti-fake gates `13a1a31`/`308ce9f` |
| 7 | **Next-gen merge + steady state (PRs #71–#75)** | 2026-08-07 → 08-16 | `04d7885` PR #71 deps; **PR #72 `d3a3eef`** next-gen architecture merge (Jul 25 prototype finally landed, after conflict-resolver chore wave `f5660a8`…); PR #73 `9586a19` verifier path; `5bf672a` sing-box export + retention; **PR #75 `da7b97f`** final next-gen+hardening (Aug 15); since Jul 30: ~12 automated runs/day, run IDs 30.56B→31.97B |

---

## 3. Branch census (50 branches)

Legend: A/B = ahead/behind main. Disposition: **DEL** = merged-lingering, safe to delete; **KEEP-EVIDENCE** = frozen donor snapshot cited by `docs/DONOR_PR_ABSORPTION_LEDGER.md`; **ACTIVE** = in use; **SALVAGE** = unique unmerged value; **DEAD-BLOAT** = dead + history-bloating.

### 3.1 Merged-but-lingering (ahead=0) — 31 branches, recommend DEL

| Branch | Last activity | Purpose |
|---|---|---|
| local `codex/open-issue-convergence` | 2026-07-27 | PR #61 convergence branch (tip `9246e2b`) |
| local+origin `feat/next-gen-architecture-and-hardening` | 2026-08-15 | PRs #72/#75 next-gen track |
| origin `fix/generated-output-verifier-path` | 2026-08-09 | PR #73 |
| origin `agent/bootstrap-legacy-cumulative-output` | 2026-07-30 | PR #69 |
| origin `agent/self-bootstrap-generated-publisher` | 2026-07-30 | PR #70 |
| origin `agent/fix-generated-output-publication` | 2026-07-30 | PR #68 |
| origin `feat/generated-outputs-publisher` | 2026-07-29 | PR #66 |
| origin `agent/resilient-fast-runtime` | 2026-07-16 | PR #56 |
| origin `agent/document-partial-run-contract` | 2026-07-15 | partial-run contract tests |
| origin `fix-mypy-type-errors-…` | 2026-06-18 | PR #42 |
| origin `fix/end-to-end-hardening-final` | 2026-06-18 | PR #43 lineage |
| origin `fix/loading-spinner-imports-…` | 2026-02-16 | PR #31 |
| origin `jules-increase-workers-timeout-buffer-…` | 2026-02-21 | PR #37 |
| origin `jules-15880732643950431958-…` | 2026-02-17 | PR #34 token precedence |
| origin `p2-badge-media-filtering-…` | 2026-02-08 | PR #28 media filtering |
| origin `task-fixes-…` | 2026-02-08 | PR #26 atomic I/O |
| origin `add-telethon-user-session-…` | 2026-02-06 | PR #13 |
| origin `enhance-logs-…`, `enrich-logging-stats-…`, `logging-improvements-…` | 2026-02-07 | PRs #14/#15/#16 logging |
| origin `jules-9848431057328374895-…` | 2026-02-07 | PR #17 CI fix + user connector |
| origin `jules-2724034965307782472-…` | 2026-02-06 | PR #4 sources/formats |
| origin `fix-cli-args-paths-…`, `fix-project-structure-…` | 2026-02-06 | PRs #5/#6 |
| origin `fix-cli-import-error-…`, `fix-missing-event-loop-…`, `fix-yaml-alias-config-…` | 2026-02-07 | PRs #19/#21/#23 |
| origin `fix-telegram-concurrency-1365…`, `fix-telegram-concurrency-6434…`, `fix-telegram-connector-retries-…` | 2026-02-06/07 | PRs #11/#12/#22 |

### 3.2 Frozen donor / partially-absorbed branches — KEEP-EVIDENCE (until ledger retires)

| Branch | A/B | Tip | Role |
|---|---|---|---|
| local+origin `feat/system-consolidation-resilience` | 42/315 | `dc3d795` | **PR #58 donor** — experimental architecture, Go engine, state-prune fixes; selectively rejected (divergent runtime, fail-open governance) but cited verbatim in ledger |
| origin `claude/repo-audit-optimization-2y7erg` | 12/336 | `443d169` | **PR #59 donor** — Claude's defensive audit (zip-bomb accounting, TOCTOU, atomic UTF-8, prune safety); "fully absorbed" per ledger |
| origin `codex/ultra-resilient-partial-workflows` | 27/264 | `99b563f` | safenet/health-envelope work (last-known-good release safenet, residue/delivery metrics). **Not in main** (grep "safenet" on main = 0) — only the #65 slice landed |
| origin `fix/publish-post-on-change-mode` | 18/265 | `dd7bae7` | publishing-mode contract tests, minority-source-failure rule — unmerged |

### 3.3 Active

| Branch | A/B | Role |
|---|---|---|
| `main` / `origin/main` | 0/0 (+1) | production; automated output commits every ~2h |
| origin `generated-outputs` | 180/909 | **publication mirror** — github-actions[bot] "Publish HUNTX outputs from run …" (born Jul 29; latest run 31970163001). Do not delete |

### 3.4 Dead state mirrors — DEAD-BLOAT

| Branch | A/B | Last | Notes |
|---|---|---|---|
| origin `huntx-state` | 39/909 | 2026-02-16 | huntx-bot "Update state [skip ci]" — commits **44–51 MB `state.db` blobs** (top history blobs, §8) |
| origin `mergebot-state` | 11/909 | 2026-02-09 | mergebot-bot predecessor of the above |

### 3.5 Unmerged with unique value — SALVAGE candidates

| Branch | A/B | Unique content | Verdict |
|---|---|---|---|
| origin `fix-db-locking-in-ingest-…` | 6/579 | `38e791f`/`c59c815` **"Fix database is locked error in Ingest Pipeline" + MTProto disconnect task-leak fix** — verified NOT ancestors of main | **Salvage**: real bug fix never merged (superseded by Jul hardening? needs re-test) |
| origin `jules-15540508145391148341-…` | 3/579 | same DB-lock fix lineage (PR #39/#40 merged only *into this branch*, never to main) | Salvage (same) |
| origin `deep-technical-audit` | 1/522 | `4a50285` v0agent comprehensive audit report docs | Archive as doc; findings already re-derived in Jun audit era |
| origin `huntx-audit-fixes-…` | 1/515 | `91be51e` post-merge follow-up commit (branch evolved after PR #41 merged) | Review 1 commit, then DEL |
| origin `codex/fix-go-123-cache-restore` | 1/264 | `b4e3bb6` Go 1.23 cache-restore collision fix | Check if PR #61/62 already fixed; likely DEL |
| origin `fix/repair-production-action-pins-20260712` | 1/489 | `ce9fe94` action pin refresh | Superseded by later pins; DEL |
| origin `agent/pipeline-workflow-performance` | 1/427 | `bd48415` pipeline/CI optimization | Mostly absorbed by PR #51; DEL after diff review |
| origin `feat-72h-rule-and-artifacts-…` | 2/892 | early 72h-rule variant | Superseded (72h logic in main since Feb); DEL |
| origin `fix/verify-pr-suggestions-…` | 2/900 | `b6f6c56`/`02024de` pre-PR#1 finalization | Ancient; DEL |
| origin `update-telegram-72h-artifacts-…` | 1/892 | `2df7fe8` 72h lookback variant | Superseded; DEL |
| origin `fix-prod-config-validation-…` | 1/847 | `7b91122` config destinations fix | Superseded by `a1981ec`; DEL |

---

## 4. Hidden / experimental / disabled feature register

| # | Feature | Location | Evidence | Status | Verdict |
|---|---|---|---|---|---|
| H1 | **UnifiedOrchestrator + 5 next-gen engines** (resilience `AsyncCircuitBreaker`, scoring `ProxyScoringEngine`, geo_routing, self_healing daemon, streaming chunk parser) | `src/huntx/core/unified_orchestrator.py`, `resilience.py`, `scoring.py`, `geo_routing.py`, `self_healing.py`, `formats/streaming.py` | Born `07e2365` (Jul 25), merged via PRs #72/#75; exported in `src/huntx/__init__.py:1-8`; imported **only by tests** (`tests/test_unified_orchestrator.py`) — production CLI never instantiates it | **Merged but dormant** | **Revive selectively**: scoring + self-healing + streaming are tested and spec-complete (conductor track 1); wire behind a flag after contract review. Do NOT revive as default orchestrator yet |
| H2 | **cmd/huntx-engine (Go next-gen runtime)** | `cmd/huntx-engine/` (main.go, georoute/, healing/, stream/, benchmark/) | Added in PR #72 conflict wave; **never built by CI** (only `cmd/huntx-tools` is built: `.github/workflows/huntx.yml:122,187,338,616`); `cmd/huntx-engine/go.mod` declares **`go 1.26`** (nonexistent toolchain) | Dormant prototype, unbuildable as declared | **Drop or quarantine** — PR #58's "divergent Go runtime" was explicitly rejected in convergence; keep as reference only |
| H3 | **latency_benchmarker** | `src/huntx/core/latency_benchmarker.py` | Exported in `__init__.py:2`; tested (`test_latency_benchmarker.py`, `test_pr72_review_regressions.py`); **no production call site** | Dormant (conductor track 2 "latency gate" only half-wired) | **Revive** — small, tested, directly implements the track-2 spec |
| H4 | **Interactive GatherX bot** (13 commands, admin elevation, delivery resume) | `src/huntx/bot/` (interactive.py, admin.py, delivery.py, handlers.py) | Live via `huntx bot` subcommand (`cli/main.py:57-96,166-191`); not run in CI; governance flags `HUNTX_ADMINS` (admin.py:17), `HUNTX_BOT_NO_PUBLISH` (admin.py:149), `HUNTX_ALLOW_SHARED_BOT_TOKEN` fail-closed (interactive.py:52-56); F-09 shared-token 409 warning (main.py:182) | Live but manually-run | Keep — issue #47 hardening is merged |
| H5 | **Encrypted-format decoders with embedded fallback keys** | `src/huntx/formats/common/crypto.py:128-130` (`.tut`/`.sks`/`.tmt` passwords `b"fubvx788b46v"`, `b"dyv35224nossas!!"`, `b"fubvx788B4mev"`), HAPP RSA keys via `HUNTX_HAPP_CRYPT*_PEM` or `persist/keys/happ_*.pem` (crypto.py:19-34), `HUNTX_NETMOD_KEY` (crypto.py:240) | Formats registered in `register_builtin.py:14-18` (slipnet/tut/sks/tmt); HAPP keys moved to env in `32f1036` (F-04 audit fix) but tut/sks/tmt **fallback passwords remain hardcoded in source** | Live decoders; partially-secret material in-tree | Keep decoders; **extract fallback passwords to env/config** (risk §8) |
| H6 | **v2ray_collector Go connector** | `src/huntx/connectors/v2ray_collector/` (main.go 649 lines, telegram_channels.json 149 channels) | Ported from sibling repo "smgo"/compare by Antigravity AI (`fec2777`, `686b02b`, merged `52c9c98`); wired into orchestrator (+12 lines); outputs gitignored | Live | Keep |
| H7 | **Anti-fake CI gates** | `.github/workflows/huntx-real-investigation-gate.yml`, `huntx-telegram-activity-gate.yml` | Born `13a1a31`/`308ce9f` (Jul 29); parse `HUNTX_RUNTIME_DIAGNOSTICS_BEGIN/END` markers from `scripts/report_runtime_health.py:166,186` to prove real Telegram activity occurred | Live, unusual | Keep — institutional knowledge: the project defends against its own CI faking runs |
| H8 | **temp_bot_init/ & temp_data_interactive/** | repo root (untracked, gitignored since `6990bc4`) | Each contains **`bot.session` (28 KB Telethon session file = live credential)**, archive/dist/outputs subdirs, dated Jul 27 | Local-only credential artifacts | **Drop from disk after session rotation**; never commit (gitignore holds) |
| H9 | **temp_state.db** (217 KB) | repo root, untracked | Was tracked; removed in `4d91077` "chore: remove tracked temp_state.db artifact"; gitignored | Local scratch DB | Drop; hygiene already done |
| H10 | **data_archive/** (410 tracked files, ~810 MB on disk) | `data_archive/all_sources_*.{npvt,ehi,hc,nm,ovpn,opaque_bundle,…}` | Historical output snapshots from Feb 2026 (epoch 1770628225 ≈ 2026-02-09), committed by skip-ci bot (`1d611e6`) | Tracked dead weight | **Untrack + archive externally** — pure bloat, no code references |
| H11 | **outputs/ vs outputs_dev/** | both tracked, both in `.github/huntx-generated-files.txt` (12 managed paths) | outputs/ = merged subscription artifacts (10 files incl. sing-box export added `5bf672a`); outputs_dev/ = cumulative deduped URIs (16 files incl. chunked `proxies_chunk_NNNN.txt`); both rewritten every 2h by the publisher | Live, divergent by design | Keep both (documented in `docs/GENERATED_OUTPUTS_MODEL.md`) |
| H12 | **persist/** | untracked runtime state: `state.db` 135 KB + WAL/SHM, `data/{archive,artifacts,dist,logs,outputs,outputs_dev,raw,rejects,state}` | Live local runtime state; `persist/data/logs/huntx.log` present; gitignored | Live | Keep |
| H13 | **.tmp/** | actionlint.exe (8.8 MB), gocache/gomod/gotmp, `donor_review/{Abzar,PSG}` (full checkouts of two **external donor repos** reviewed during convergence), `pr-body.md` | Agent scratch from Jul 27 donor-review session | Scratch | Drop (untracked) |
| H14 | **Stash@{0}** (2026-08-16) | `!!GitHub_Desktop<main>` | Contains a **previous PenguinHarness forensic report** `forensic-investigation/README.md` (44 lines, dated 2026-08-16, "HEAD inspected: main @ 7528f9e") + output churn | Prior investigation artifact | Preserve content elsewhere, then drop |
| H15 | **Stash@{1}** (2026-07-25, on `f23eb8a`) | WIP of the entire next-gen track: huntx-engine Go sources **plus 4.5+4.7 MB `.exe` binaries**, conductor tracks, MASTER_FORENSIC_COMPENDIUM, superpowers plan, deletion of `outputs/verify_output.py` | The Jul-25 conductor session's uncommitted draft — most of it was later committed properly | Historical | Drop (binaries should never be committed) |
| H16 | **ROADMAP.txt** | deleted in `cf64f63` (day 1) | Recoverable via `git show 1a2a738:ROADMAP.txt` — AI refusal + ETL roadmap = the repo's founding document | Deleted | Preserve as provenance (history only) |
| H17 | **HuntX_Master_Audit_Report.md** | created `75eddc3` (Apr 29), deleted `7004d29` (May 22) | Recoverable from history | Deleted | History only |
| H18 | **scripts/systemd/mergebot.service** | stale unit referencing `/opt/mergebot` + `mergebot` user | Pre-rebrand legacy | Dead | Drop or rename to huntx |
| H19 | **full_audit_report.md** (49 KB, root) | committed `99c59ab` (Jun 13) | June audit evidence; superseded by docs/history/* ledger chain | Tracked, semi-dead | Move to docs/history/ |
| H20 | **Agent index dirs** (.codegraph, .serena, graphify-out, .cocoindex_code, .smart-coding-cache, .code-review-graph) | gitignored since `6990bc4` era | Tool caches | Untracked | Keep local |
| H21 | **TODO/FIXME/XXX/HACK census** | src/, cmd/, internal/, scripts/ | **0 matches** — the codebase is marker-clean (only 3 "deprecated" mentions, all about avoiding deprecated `get_event_loop`) | Clean | — |
| H22 | **.data/vectors/** | empty dir | Unknown origin | Empty | Drop |

---

## 5. Conductor track register

`conductor/` born `f23eb8a` (2026-07-25 14:59) — "conductor(setup): Initialize project context and standards" (index.md, product.md, tech-stack.md, workflow.md, code_styleguides/).

| Track | Dir | Status | Goal (from spec.md) | Outcome |
|---|---|---|---|---|
| **Next-Gen Architecture** (Zero-Copy Streaming, Geo-Clustering, Autonomous Self-Healing) | `conductor/tracks/next_gen_architecture_20260725/` (index/spec/plan) | marked complete `a2736a8` (Jul 25) — plan checkboxes still unchecked | 1) `StreamingChunkParser` 64KB chunks <50MB RAM; 2) `GeoRoutingEngine` protocol+country/ASN taxonomy; 3) `SelfHealingDaemon` backoff 5m→15m→1h→6h, purge >48h dead nodes; 4) integrate in `UnifiedOrchestrator` with `AsyncCircuitBreaker` | All 4 components exist + tested (H1), merged via PRs #72/#75, but **never wired into production path** — track "complete" in code, dormant in runtime |
| **Hardening & Health Benchmarking** | `conductor/tracks/resilience_monitoring_20260725/` (+metadata.json `"status": "completed"`, created 2026-07-25T15:00Z) | completed | 1) proxy latency gate (>3000ms filtered); 2) decoder edge-case test expansion; 3) bot freshness alerts | Partially live: decoder tests + freshness alerts exist; latency gate = H3 (implemented, tested, **not called in pipeline**) |

---

## 6. Automated-commit mechanics

**Generation 1 (2026-02-09 → 2026-05-21):** CI pushed directly with bot identities.
- `huntx-bot`: 254× "Update outputs [skip ci]" → main (rewrote outputs/ + outputs_dev/, ~164k-line churn per commit, sample `9991310`).
- `huntx-bot`/`mergebot-bot`: "Update state [skip ci]" → **state branches only** (`huntx-state`, `mergebot-state`), committing 44–51 MB `state.db` binaries — the origin of the history bloat. `state.db` was **never on main** (0 main commits touch it).

**Generation 2 (2026-07-29 → present, PR #66 control plane):**
- `.github/workflows/huntx.yml` ("huntx-production"): cron `0 */2 * * *` + workflow_dispatch (inputs: max_workers, lookback hours, reset w/ `RESET-HUNTX-STATE` confirmation). Env hardening: `HUNTX_RUN_TIMEOUT=5400`, `HUNTX_COMPLETION_BUFFER=900`, `HUNTX_ALLOW_PARTIAL_EXPORT=true`, pinned actions by SHA.
- On success → `publish-generated-outputs.yml` (workflow_run trigger, born `4d4447b`): validates source run id/attempt, assembles snapshot (`scripts/assemble_generated_snapshot.py`), github-actions[bot] commits **"Publish HUNTX outputs from run <run_id>/<attempt>"** to `generated-outputs` branch, then `scripts/sync_generated_outputs_to_main.py` mirrors the 12 managed paths (`.github/huntx-generated-files.txt`) to main as **"Update HUNTX outputs from run <run_id>/<attempt>"**.
- Run-ID pattern: GitHub Actions run ID + attempt (`31964506908/1`); IDs ascend ~30.56B (Jul 30) → 31.97B (Aug 16).
- Cadence: 176 main commits over 17 days ≈ **10–12 runs/day** (2h cron). Post-merge gates then verify real investigation + Telegram activity (H7).

---

## 7. Knowledge preservation (recoverable ONLY from history/branches)

1. **Why monkey-patches instead of refactors:** `runtime_resilience.py` (born `c405167`) patches `OptimizedHardenedOrchestrator` at import time (`hardened_main.py:22 apply_runtime_resilience()`) because the Jul-12→16 hardening wave had to ship invariants **without touching the frozen orchestrator hierarchy** mid-production; `install_transform_contract()`/`install_dev_manifest_contract()` (runtime_resilience.py:21-22) enforce bounded contracts the same way. `docs/solutions/lessons-learned.md` records the operational reasons (conflict-marker hygiene after stashes, LSP-invariant signatures for mypy, Windows pytest `--basetemp`).
2. **Why the next-gen prototype died then half-revived:** PR #58's architecture was rejected *selectively* at convergence (`docs/history/CONVERGENCE_2026-07-27.md`, `docs/DONOR_PR_ABSORPTION_LEDGER.md`): divergent Go/Python runtime + fail-open governance = "Negative guardrail / Rejected"; resilience/scoring/geo/self-healing/streaming = "Adapted", re-landed via PRs #72/#75 on the Python-native path. Frozen donor SHAs: PR #58 = `dc3d795`, PR #59 = `443d169`, PR #60 = dependabot.
3. **Unmerged fixes at risk of being lost:** the **"database is locked" + MTProto disconnect-leak fix** (`38e791f`, `c59c815` on `fix-db-locking-in-ingest-…` / `jules-15540508145391148341-…`) never reached main; the **ultra-resilient safenet suite** (27 commits on `codex/ultra-resilient-partial-workflows`: last-known-good release safenet, residue/delivery degradation metrics) only partially landed via #65.
4. **Who did what:** single human owner (Farnam Taheri, 470 commits under 3 identities); Jules = June audit+mypy; Antigravity AI = v2ray_collector port; Claude = PR #59 defensive audit (branch-only, 12 commits); v0agent = June audit report (branch-only); CodeRabbit = 1 auto-fix; Codex = convergence branch + CI fixes.
5. **Provenance:** repo founded from an AI roadmap that includes the model's own refusal (`1a2a738:ROADMAP.txt`); two sibling repos merged in — **GATHEREX** (Feb 10, bot/frontend identity) and **compare/main / smgo** (Jun 11–12, Go collector + session locking "ported from duplicate repository" `9008089`).
6. **State-schema archaeology:** v10 migration deliberately preserves `record_verdicts` verdict cache (`174d430`, guarded by `src/huntx/state/migration_safety.py:54-72`).
7. **Prior investigation:** stash@{0} holds a complete 2026-08-16 PenguinHarness forensic report (README index of 10 phase docs) — evidence this repo was already investigated once; its conclusions align with this report.

---

## 8. Risks (history-derived)

| Risk | Evidence | Severity |
|---|---|---|
| **History bloat:** 2.55 GiB pack; top blobs = 70 MB `outputs/all_sources.opaque_bundle` + **24× 43–51 MB `state.db` blobs** (all on `huntx-state`/`mergebot-state` branches); 1.50 GiB of `tmp_pack_*` garbage in `.git/objects/pack/` (interrupted fetch/gc) | `git count-objects -vH`; blob census | High — clones are multi-GB; cleanup requires deleting state branches + `git filter-repo` (destructive; maintainer decision) |
| **Output churn in history:** every 2h commit rewrites ~430k lines (outputs_dev/proxies.{json,txt}); history grows ~1–2 MB/run forever | `git show 8ffd830 --stat` (221k ins / 214k del) | Medium — consider LFS or artifact-only publication |
| **No credential files ever committed** — verified: `git log --all --diff-filter=A` for `*.session/*.pem/*.key/*.env/token/secret` returns only code files (`session_lease.py`, `make_telethon_session.py`, tests). `configs/config.prod.yaml` uses `${ENV}` expansion throughout | clean | OK |
| **Hardcoded decryption passwords in source:** `.tut/.sks/.tmt` format passwords committed in plaintext (`src/huntx/formats/common/crypto.py:128-130`); HAPP RSA keys properly env-loaded since `32f1036` | crypto.py | Medium — rotate/externalize if formats are third-party-licensed |
| **Live Telethon session files on disk (untracked):** `temp_bot_init/bot.session`, `temp_data_interactive/bot.session` (28 KB each) | worktree | Medium — session = account credential; `.gitignore` covers `*.session` but local exposure remains |
| **Local main 1 commit behind origin** (`473d8f9`); GitHub Desktop stash marker present; 2 stashes incl. binaries in stash@{1} | for-each-ref, stash list | Low |
| **`cmd/huntx-engine/go.mod` declares `go 1.26`** — unbuildable with real toolchains; root `go.mod` says 1.23.1 | go.mod files | Low (dormant code) |
| **Abandoned-but-cited branches:** deleting donor branches would break ledger SHA references (`dc3d795`, `443d169`) | DONOR_PR_ABSORPTION_LEDGER.md | Low — keep until ledger retired |

---

## Appendix — key SHA index

| SHA | Meaning |
|---|---|
| `1a2a738` | Initial commit (ROADMAP.txt) |
| `48afeae` | REBRAND mergebot→huntx (2026-02-10) |
| `58f6949` / `a501f12` | LTS1.0 / v1.1-lts |
| `52c9c98` | compare/main merge (v2ray_collector) |
| `bb910cd` / `189025a` | HardenedOrchestrator / OptimizedHardenedOrchestrator born |
| `d8ec8e5` / `623f886` / `c405167` | hardened_main / GovernedBuild / runtime_resilience |
| `f23eb8a` / `07e2365` | conductor init / UnifiedOrchestrator+Compendium |
| `6ac5ef7` | PR #61 convergence merge |
| `4d4447b` | publish-generated-outputs workflow born |
| `d3a3eef` / `da7b97f` | PR #72 / PR #75 next-gen merges |
| `dc3d795` / `443d169` | frozen donor tips (PR #58 / PR #59) |
| `38e791f` / `c59c815` | unmerged DB-lock fixes |
| `8ffd830` / `473d8f9` | local / origin main HEAD |
