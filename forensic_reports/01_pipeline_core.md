# Subagent A — HUNTX Pipeline Core Forensics
Scope: `src/huntx/core/`, `pipeline/`, `state/`, `store/` (+ `cli/` for call-path tracing) · 41 files · 8,476 LOC
Repo: `D:/GitHub/HUNTX` · HEAD `8ffd830` · All citations verified file:line.

**Live-verification status:** ✅ = confirmed by reading exact source or running grep; 🔍 = derived/inferred; ⚠️ = stale-risk.

---


## 1. Entry points & the single live execution path

Production entry: `pyproject.toml:31` → `huntx = "huntx.cli.hardened_main:main"` (also `src/huntx/__main__.py:1`).
CI (`.github/workflows/huntx.yml:414`) invokes `huntx --config configs/config.prod.yaml --data-dir persist/data --db-path persist/state.db run …` under a 105-min watchdog.

**Live call chain (verified):**
```
hardened_main.main()                      hardened_main.py:186-189
 ├─ apply_runtime_resilience()            hardened_main.py:22  (import-time monkey-patch, runtime_resilience.py:295-305)
 │   ├─ install_transform_contract()      runtime_resilience.py:21 → transform_contract.py:15 (wraps HardenedOrchestrator._run_hardened)
 │   └─ install_dev_manifest_contract(Orchestrator)  runtime_resilience.py:22 → dev_manifest_contract.py:75
 ├─ legacy._cmd_run = _cmd_run            hardened_main.py:187 (replaces cli/main.py:105 _cmd_run)
 └─ hardened_main._cmd_run                hardened_main.py:80
     ├─ OptimizedHardenedOrchestrator     hardened_main.py:115
     ├─ reconcile_configured_bot_consumers  hardened_main.py:120 (consumer_reconciliation.py:142)
     ├─ build_pipeline := GovernedBuildPipeline  hardened_main.py:129 (replaces BuildPipeline)
     ├─ orchestrator.run()                → HardenedOrchestrator.run (hardened_orchestrator.py:41)
     │   └─ run_sync(self._run_hardened)  → runtime_resilience._run_hardened (patched)
     │       ├─ _canonical_ingestion_sources (runtime_resilience.py:70, patched)
     │       ├─ PersistentIngestionQueue.recover_expired_leases / seed_rolling_horizon
     │       └─ HardenedOrchestrator._run_hardened (transform_contract-wrapped) → original body
     │           ├─ Phase 1 ingestion: _worker_async (OptimizedHardenedOrchestrator, optimized_orchestrator.py:303)
     │           │    ├─ direct sources → _run_direct_source → Orchestrator._ingest_one_source_async → IngestionPipeline.run
     │           │    └─ telegram_user  → _run_persistent_windows → WindowedIngestionPipeline.run_page
     │           ├─ Phase 2 transform: OptimizedTransformPipeline.process_pending (deadline-bound by transform_contract)
     │           ├─ Phase 3 build: GovernedBuildPipeline.run (ThreadPool) → publish: PublishPipeline.run (ThreadPool)
     │           ├─ export: _export_outputs + _export_dev_outputs (dev-manifest-normalised)
     │           └─ cleanup: prune_processed / prune_orphans / prune_archive
     └─ evaluate_run_health / emit_run_health → health gate (hardened_main.py:141-158)
```
`state/__init__.py:12-14` installs three monkey-patches at import: `install_migration_safety(DBConnection)`, `install_state_repo_hardening(StateRepo)` (replaces `record_file` with atomic `_record_file_atomic`, repo_hardening.py:229-236, and adds bot-consumer methods), `install_consumer_reconciliation(StateRepo)`.

## 2. Orchestrator lineage (4 classes, 1 live)

| Class | File:line | Status |
|---|---|---|
| `Orchestrator` | core/orchestrator.py:39 (719 LOC) | **LIVE as base**: wiring (`__init__` :60-108), exports (:114-317), `_ingest_one_source_async` (:335-410), `run()` (:432-449). `_run_async` (:451-468) delegates to `HardenedOrchestrator._run_hardened` via lazy import (import-cycle workaround). |
| `HardenedOrchestrator` | core/hardened_orchestrator.py:38 | **LIVE**: authoritative stage machine `_run_hardened` (:52-363) — bounded ingestion/build/publish pools, deadline accounting, status classification `_classify_completed_status` (:13-35), structured summary. |
| `OptimizedHardenedOrchestrator` | core/optimized_orchestrator.py:20 | **LIVE (production class)** but its own `_run_hardened` (:324-401) and `_canonical_ingestion_sources` (:112-169) are **shadowed** by runtime_resilience.py:299-304 patches. Live members: `__init__` (:23-44), env tunables (:46-104), `_worker_async` (:303-322), `_run_direct_source` (:171-204), `_run_persistent_windows` (:206-301). |
| `UnifiedOrchestrator` | core/unified_orchestrator.py:22 | **DEAD** prototype (git `07e2365`/`6ae19a9` "Next-Gen Architecture" track). Only refs: `src/huntx/__init__.py:1` export + `tests/test_unified_orchestrator.py`. `_run_unified` (:80-131) **skips ingestion entirely**, no `min_seen_file_id`, no export/cleanup; instantiates never-called engines (circuit breaker, scoring, streaming parser, geo routing, self-healing). |

**Shadowed-code bug preserved in history:** the class-version `_run_hardened` (optimized_orchestrator.py:324-401) never assigns `self.config.sources = ingestion_sources`, so alias exclusion would not reach the stage machine; the patch fixes it (runtime_resilience.py:230). The patch also adds preflight-time budgeting, canonical-resolution timeouts (`HUNTX_CANONICAL_RESOLVE_TIMEOUT`), connector reuse across resolutions, and guaranteed connector close (runtime_resilience.py:256-259).

## 3. Live/dead map (all 41 scope files)

**LIVE — core:** orchestrator.py (partial), hardened_orchestrator.py, optimized_orchestrator.py (partial), runtime_resilience.py, transform_contract.py, dev_manifest_contract.py, run_health.py, locks.py, session_lease.py (partial: only `session_lease_path` used at hardened_main.py:110 with sync `acquire_lock`).
**LIVE — pipeline:** ingest.py, windowed_ingest.py, transform.py (base for optimized), optimized_transform.py (production transform), build.py, governed_build.py, publish.py.
**LIVE — state:** db.py (schema+migrations v1-v10), repo.py (+ repo_hardening.py patch), ingestion_queue.py, verdict_store.py (`get_records_for_governed_build` only), consumer_reconciliation.py, migration_safety.py, `__init__.py`.
**LIVE — store:** paths.py, raw_store.py, artifact_store.py, release_manifest.py (NOT — see below).
**LIVE — cli:** hardened_main.py; main.py (only `_deliver_updates`, `_cmd_bot`, clean/reset/prune helpers remain reachable via subcommands).

**DEAD / unreachable in production:**
- `Orchestrator._run_async_legacy` (orchestrator.py:470-719, ~250 LOC) — zero callers. **Only place `repo.prune_old_data` runs automatically** (see Defect D3).
- `UnifiedOrchestrator` + its 5 engines: `core/resilience.py` (AsyncCircuitBreaker), `core/scoring.py` (ProxyScoringEngine), `core/geo_routing.py` (GeoRoutingEngine), `core/self_healing.py` (SelfHealingDaemon — owns a *separate* sqlite `degraded_proxies` DB, self_healing.py:47-61), `formats/streaming.StreamingChunkParser` — all exported in `src/huntx/__init__.py:1-14`, exercised only by tests.
- `core/latency_benchmarker.py` — export + tests only; never invoked by any pipeline.
- `core/verdicts.py` (SyntaxVerdict/ProbeVerdict/PolicyVerdict/PublicationDecision) — tests only (`tests/test_verdicts.py`).
- `state/verdict_store.py:upsert_record_verdict` — **zero callers anywhere** (see Defect D4).
- `state/lifecycle.py` (`record_source_event`, `get_source_lifecycle`) — tests only; `source_lifecycle` table never written in production (see Defect D5).
- `store/rejects.py:RejectsStore` — zero callers in src (only `paths.REJECTS_DIR` plumbing).
- `store/release_manifest.py` — tests only (`tests/test_release_governance.py`); CI verifies outputs with the Go tool `.bin/huntx-tools verify-output` instead (huntx.yml:443).
- `cli/commands/run.py:run_command` — tests only (`tests/test_audit_remediation.py:90`); uses base `Orchestrator`.
- `cli/main.py:_cmd_run` — replaced at runtime by hardened_main.py:187; reachable only if `huntx.cli.main` is invoked directly (no entry point).
- `PublishPipeline._hash_cache` / `_last_published_hash` / `_remember_published_hash` (publish.py:32,47-57) and `StateRepo.is_artifact_published` (repo.py:492) — dead; the publication-intent ledger superseded hash-diff skipping.
- `session_lease.acquire_session_lease` (async heartbeat lease, session_lease.py:170-220) — tests only; production uses plain `acquire_lock` on the same path.
- `Orchestrator._seen_channels` dedup (orchestrator.py:103,376-386) — unreachable in production: the optimized worker routes all `telegram_user` sources through the LIFO window queue, never through `_ingest_one_source_async`'s MTProto branch (optimized_orchestrator.py:311-322).

## 4. Schema summary (state/schema.sql · 215 lines · user_version 10)

**Tables (15):** `source_state` (connector offsets), `source_lifecycle` (trust — *unused in prod*), `seen_files` (observations; UNIQUE(source_id, external_id); status pending/processed/failed/ignored), `records` (parsed proxies; `unique_hash` identity, `is_active`, `source_observation_id` FK→seen_files ON DELETE RESTRICT), `record_verdicts` (PK(unique_hash, record_type, policy_tier); syntax/probe/policy statuses — *no production writer*), `published_artifacts`, `publication_intents` (UNIQUE(publication_key, artifact_hash, generation)), `publication_deliveries` (state machine desired/sending/confirmed/failed/unknown_outcome/skipped), `telegram_bot_updates` (durable bot inbox), `telegram_bot_consumers` (watermarks), `bot_users`, `bot_delivery_checkpoint`, `bot_delivery_items`, `ingestion_campaigns`, `ingestion_work_items` (LIFO windows; lease_owner/lease_token/lease_expires_at, rotation_seq, UNIQUE(source_id, window_start_ts, window_end_ts)). 20 indexes incl. `idx_ingestion_work_lifo` (status, window_end_ts DESC, rotation_seq ASC).

**Migrations** (db.py:67-336): v1 seen_files cols → v2 rotation_seq → v3 bot_delivery_items → v4 publication ledger → v5 records.source_observation_id (observation provenance) → v6 bot_users.approved → v7 telegram_bot_updates → v8 lease_token → v9 telegram_bot_consumers → **v10 VMess canonicalisation re-key** (db.py:275-333: rewrites `records.unique_hash`+`data_json` for sorted-key canonical VMess URIs, copies verdicts to new hashes, then deletes unreferenced verdicts). Each step has postcondition checks that raise on failure. `migration_safety.py:50-98` wraps `_check_migrations` to snapshot/restore verdict rows the v10 sweep would over-delete.

**DB contract** (db.py:14-16,338-355): WAL + `synchronous=FULL` (explicit durability contract, db.py:52-55), busy_timeout 30 s, 32 MiB cache, 256 MiB mmap, FK ON, per-call connection with commit/rollback. WAL is redundantly re-set in orchestrator.py:86-90.

## 5. Data flow (live path)

1. **Ingest** — `IngestionPipeline.run` (ingest.py:84-221): iterate connector items (sync or async), 100-item batches; `_process_batch` (:17-82) dedups by `(source_id, external_id)` + sha256 compare against `seen_files.raw_hash`, saves blob via `RawStore.save` (content-addressed, 2-char sharding, digest re-verified on disk — raw_store.py:46-70), inserts observations `pending`; `acknowledge` hook per batch; source state + stats persisted at end. Windowed variant (windowed_ingest.py:94-144) reuses one MTProto connector across pages keyed by (api_id, api_hash, session) and commits page items + queue checkpoint in **one transaction** (:118-133).
2. **LIFO queue** — `PersistentIngestionQueue` (ingestion_queue.py:25-368): seeds closed epoch-aligned windows over a lookback horizon (:48-125), strict newest-window-first claim with `BEGIN IMMEDIATE` + lease token (:144-205), checkpoint/fail/terminal/release transitions all lease-token-guarded (rowcount!=1 ⇒ RuntimeError, :249-250 etc.), rotation_seq advanced after every page for fair source rotation (:42-46).
3. **Transform** — `OptimizedTransformPipeline.process_pending` (optimized_transform.py:33-150): bounded by deadline/max_batches/max_records (env-tunable, transform.py:23-33); per-file parse in ThreadPool (`_process_single_file` transform.py:57-160 — no DB writes), format routing via `decide_format` (router.py:62-86, LRU-cached extension table + proxy-URI/b64 content heuristics), per-file record cap `HUNTX_TRANSFORM_MAX_RECORDS_PER_FILE`; `_flush_batch` (transform.py:162-186) commits records + observation status flips in **one transaction** (atomicity contract documented at repo.py:358-370).
4. **Build** — `GovernedBuildPipeline` (governed_build.py:45-133): per-route policy (publication_tier, require_fresh_probe from config/schema.py:139-146), single-flight query reuse for equivalent routes (:76-110), delegates to fresh `BuildPipeline` per route sharing format locks. `BuildPipeline.run` (build.py:265-418): `get_records_for_build` dedup query (repo.py:428-490 — DISTINCT fan-out guard + MAX(id) dedup CTE), handler.build under per-format lock, `ArtifactStore.save_artifact` (content-addressed internal) + `save_output` (data/outputs, archive-on-change), derivative artifacts for `npvt`/`npvtsub`: `.decoded.json`, `.b64sub`, `.singbox.json` (build.py:246-263,343-383).
5. **Publish** — `PublishPipeline.run` (publish.py:59-242): payload sha256 must equal `artifact_hash` (:68-70); empty-zip skip ≤22 bytes (:73-75); durable intent via `ensure_publication_intent`; per-destination delivery state machine; **`unknown_outcome` permanently blocks auto-resend** until manual reconciliation (:171-179); per-token publisher instances with locks (:35-45); token fallback warning F-09 (:80-87); all-confirmed completes intent + `mark_published`.
6. **Export** — `_export_outputs` (orchestrator.py:114-216): route files to `paths.output_dir` with 3-day retention pruning of stale route-owned files (`HUNTX_OUTPUT_RETENTION_DAYS`); `_export_dev_outputs` (:222-317): all-time cumulative proxies.txt/json/b64sub keyed by `_manifest.json` {uri→first_seen}, dedup by `strip_proxy_remark`; manifest canonicalised beforehand by dev_manifest_contract.py:20-65 (earliest-first merge).
7. **Health gate** — `evaluate_run_health` (run_health.py:45-206) classifies fatal/degraded/success from the summary; fatal ⇒ exit 1 (hardened_main.py:143-150); degraded succeeds with reasons; optional JSON envelope to `HUNTX_RUN_SUMMARY_PATH`.

## 6. Top consolidation/defect findings (file:line)

**D1 — Four orchestrator classes; one live path; dead prototype exported as public API.**
`UnifiedOrchestrator` (unified_orchestrator.py:22-131) is exported from `src/huntx/__init__.py:1` but skips ingestion/export/cleanup and would produce stale artifacts if used. Its satellite engines (resilience.py, scoring.py, geo_routing.py, self_healing.py, latency_benchmarker.py, formats/streaming) have **no production call path**. → Absorb useful engines into the governed build/publish path or archive them; collapse Orchestrator/Hardened/Optimized into one class.

**D2 — Production behavior is defined by import-time monkey-patches, not the class source.**
runtime_resilience.py:295-305 replaces `OptimizedHardenedOrchestrator._run_hardened` and `_canonical_ingestion_sources`; transform_contract.py:73 wraps `HardenedOrchestrator._run_hardened`; dev_manifest_contract.py:84 wraps `Orchestrator._export_dev_outputs`; state/__init__.py:12-14 patches `StateRepo`/`DBConnection`. The shadowed class methods (optimized_orchestrator.py:112-169, 324-401) diverge semantically from their replacements (e.g. missing `self.config.sources = ingestion_sources`, fixed only at runtime_resilience.py:230). Reading the class alone misdescribes production. → Inline the patches into the classes; delete shadowed copies.

**D3 — 🔍 State DB never auto-pruned in production (only caller is dead code).**
`repo.prune_old_data` (repo.py:714-781, with the blob-reference safety guard :720-741) is called only from the dead `_run_async_legacy` (orchestrator.py:678-688) and manual `huntx prune` (cli/main.py:414-451). The live cleanup stage (hardened_orchestrator.py:309-319) prunes only files. `records`/`seen_files`/`published_artifacts` grow without bound under the 2-hourly CI cron; `get_records_for_build` scan cost grows with them. → Add `prune_old_data(HUNTX_PRUNE_DAYS)` to the hardened cleanup stage.

**D4 — ✅ Governed "secure" publication tier has no verdict writer (half-built feature).**
`upsert_record_verdict` (state/verdict_store.py:8-59) has **zero callers in all of `src/`** (confirmed by grep: the function is defined at verdict_store.py:8, and no other file in `src/` contains the symbol). Nothing populates `record_verdicts` (only the v10 migration copy and tests write it). `get_records_for_governed_build` with `publication_tier='secure'` (verdict_store.py:83-95) INNER-JOINs the empty table ⇒ **any route configured `secure` silently builds zero records**. The verdict model (`core/verdicts.py`), latency prober (`latency_benchmarker.py`) and `PublicationDecision.is_eligible` (`verdicts.py:52-60`) are the unfinished other half. → Wire a verdict-producing stage (syntax at transform, probe via latency_benchmarker) **or** remove the `secure` tier from the config surface entirely.

**D5 — Two parallel source-trust models; the durable one is dead.**
Production trust = config enum `SourceConfig.trust_state` → `publication_eligible` (config/schema.py:99,118-119; enforced at hardened_orchestrator.py:60). The DB model `source_lifecycle` + `record_source_event`/`get_source_lifecycle` (state/lifecycle.py, schema.sql:8-21) is tests-only; git `4c7f63d` ("enforce source trust states in hardened runs") left the durable side unwired. → Either drive lifecycle events from ingest outcomes (failure/nonempty/valid) or drop the table.

**D6 — Outputs are double-written by two components with conflicting naming/retention.**
`BuildPipeline.run` writes `data/outputs/{route}.{fmt}` via `ArtifactStore.save_output` (build.py:339, artifact_store.py:66-89, archive-on-change), then `_export_outputs` rewrites the same base files and adds derivatives as `{route}_{fmt}_decoded.json` etc. (orchestrator.py:201-216) — while `save_output` already wrote derivatives as `{route}.{fmt}.decoded.json` (build.py:347,360,373). The export's stale-prune (orchestrator.py:145-168) treats the `save_output` derivative copies as stale and deletes them after 3 days. Same directory, two naming schemes, two retention semantics. → Single writer for `outputs/`.

**D7 — Duplicated transform loop (~120 LOC ×2).**
`TransformPipeline.process_pending` (transform.py:188-321) and `OptimizedTransformPipeline.process_pending` (optimized_transform.py:33-150) are near-identical bounded loops differing only in adaptive batch size (optimized_transform.py:24-31). → Merge; keep one parameterised loop.

**D8 — Three CLI run implementations with divergent defaults.**
cli/main.py:105-163 (`HUNTX_RUN_TIMEOUT` default 9000, naive health gate), cli/hardened_main.py:80-183 (default 12600, run-health gate, governed build), cli/commands/run.py:15-70 (default 12600, base Orchestrator, tests-only). → One run command.

**D9 — Dead publish-era machinery.**
`PublishPipeline._hash_cache/_last_published_hash/_remember_published_hash` (publish.py:32,47-57) and `StateRepo.is_artifact_published` (repo.py:492-505) are unreferenced since the intent ledger; `build_result["generation"]` is never set by BuildPipeline (publish.py:89 fallback always used). Also `RejectsStore` (store/rejects.py) and `release_manifest.py` have no production callers (CI uses Go `huntx-tools verify-output`, huntx.yml:443). → Delete or wire release_manifest into CI packaging.

**D10 — Leaky ingestion boundary + pointless serialization round-trip.**
`WindowedIngestionPipeline.run_page` calls the private `IngestionPipeline._process_batch` across classes (windowed_ingest.py:119). `IngestionPipeline._process_batch` pre-serializes metadata to JSON (ingest.py:73-78, with a confused in-code comment :68-72) and `StateRepo.record_files_batch` re-parses it (repo.py:282) before calling `record_file` row-by-row (repo.py:280-292 — N SELECT+INSERT pairs per batch, no executemany). → Promote `_process_batch` to public API taking a conn; batch-insert observations with executemany.

**Minor items:** WAL set twice (orchestrator.py:86-90 vs db.py:51) · ingest progress-log condition rarely fires (ingest.py:151) · `paths.py` dual model (module globals mutated by `set_paths` :67-93 vs frozen `RuntimePaths` :24-49) creates construction-order hazards for `RawStore()`/`ArtifactStore()` defaults (raw_store.py:37) · async `acquire_session_lease` (session_lease.py:170) unused while production holds a plain file lock on the same path (hardened_main.py:110) · `get_records_for_build` returns [] when `from_sources` empty (repo.py:434) — silent empty builds if config validation is bypassed.

## 7. Env-var surface (production)
HUNTX_MAX_WORKERS(3) · HUNTX_RUN_TIMEOUT(12600) · HUNTX_ALLOW_PARTIAL_EXPORT(true) · HUNTX_ALLOW_PARTIAL_SUCCESS · HUNTX_SOURCE_TIMEOUT(600) · HUNTX_COMPLETION_BUFFER(1800) · HUNTX_INGEST_WINDOW_SECONDS(3600) · HUNTX_INGEST_PAGE_SIZE(100) · HUNTX_LIFO_LOOKBACK_HOURS(→file_fresh_hours) · HUNTX_TRANSFORM_BATCH_SIZE/MAX_BATCHES/MAX_RECORDS/MAX_RECORDS_PER_FILE · HUNTX_CANONICAL_RESOLVE_TIMEOUT(20) · HUNTX_TELEGRAM_CLEANUP_TIMEOUT(10) · HUNTX_OUTPUT_RETENTION_DAYS(3) · HUNTX_PRUNE_DAYS(30, dead path) · HUNTX_STRICT · HUNTX_RUN_SUMMARY_PATH · HUNTX_DATA_DIR · HUNTX_STATE_DB_PATH · TELEGRAM_USER_SESSION (session lock identity).

## 8. Test coverage of scope (95 test files total)
Direct: test_orchestrator.py, test_orchestrator_timeout_contract.py, test_hardened_health_gate.py, test_hardening.py, test_hardening_regressions.py, test_persistent_lifo_ingestion.py, test_transform_atomicity.py, test_ingest_pipeline.py, test_ingest_ack.py, test_build_pipeline.py, test_build_record_fanout.py, test_publish_pipeline.py, test_delivery_resume.py, test_release_governance.py, test_session_lease(.py/_reap.py), test_verdicts.py, test_source_lifecycle.py, test_unified_orchestrator.py, test_db_migrations.py, test_db_state_coverage.py, test_state_repo.py, test_observation_provenance.py, tests/perf/* (ingest/router/transform benches). Dead-code modules (Unified, geo, scoring, self-healing, latency, streaming) are kept green by tests despite zero production use — a consolidation trap (tests ≠ usage).

## 9. Consolidation recommendation (port order)
1. Inline runtime_resilience/transform_contract/dev_manifest_contract patches into the classes; delete shadowed methods (D2). 
2. Delete `_run_async_legacy` after moving `prune_old_data` into hardened cleanup (D3). 
3. Merge the two transform loops (D7); unify run commands (D8); single outputs writer (D6). 
4. Decide verdict pipeline: complete (wire `upsert_record_verdict` + prober) or excise `secure` tier (D4); same for lifecycle trust (D5). 
5. Delete dead publish hash cache, RejectsStore, commands/run.py; archive UnifiedOrchestrator + engines or productize them (D1, D9). 
6. Clean ingest boundary (D10), drop duplicate WAL, collapse paths.py to RuntimePaths.
