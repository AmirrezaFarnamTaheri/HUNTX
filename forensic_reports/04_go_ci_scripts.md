# Subagent D — Go Code, CI/CD, Scripts & Build Plumbing

Repo: `D:/GitHub/HUNTX` · Read-only static analysis (no Go toolchain available; CI runs the builds/tests) · 2026-08-17

**Live-verification status:** ✅ = confirmed by reading exact source; 🔍 = derived/inferred; ⚠️ = stale-risk (requires Go toolchain or live CI to verify fully).

---


## 1. Go inventory — the "754 .go files" mystery RESOLVED

`find . -name '*.go' -not -path './.git/*' | wc -l` → **754**. Breakdown:

| Location | .go files | What it is |
|---|---|---|
| `.tmp/gomod/**` | **737** (23 MB) | **Local Go module cache** — `actionlint@v1.7.12`, `golang.org/x/sys@v0.42.0` (342 unix + 58 cpu + 26 windows…), `uax29/v2`, `robfig/cron/v3`, `go.yaml.in/yaml/v4`, `mattn/*`, `fatih/color`, `x/sync`. Gitignored (`.gitignore:18` `.tmp/`). NOT project code. |
| `cmd/huntx-engine/**` | 10 | Next-gen Go engine (5 pkgs + main, 5 test files) |
| `cmd/huntx-tools/` | 1 | Release-plane CLI |
| `internal/**` | 4 | outputverify, releasemanifest, runtimegen, sitegen |
| `src/huntx/connectors/v2ray_collector/` | 1 | Telegram scraper (own module) |
| **Project total** | **17** (+2 committed `.exe`) | 2,534 LOC of Go |

### Module structure (3 modules)

| Module | go.mod | Deps | Notes |
|---|---|---|---|
| `github.com/AmirrezaFarnamTaheri/HUNTX` | root `go.mod` — `go 1.23.1`, **no require, no go.sum** | none | Owns `internal/*` + `cmd/huntx-tools`. CI `go-version-file: go.mod` → Go 1.23.x toolchain. |
| `huntx-engine` | `cmd/huntx-engine/go.mod:1-3` — `go 1.26` | none | **Nested module ⇒ excluded from root `go test ./...` / `go vet ./...` wildcards.** `go 1.26` directive won't even build under CI's 1.23 toolchain. |
| `huntx-collector` | `src/huntx/connectors/v2ray_collector/go.mod` — `go 1.21` | `goquery v1.8.1` (+cascadia, x/net), go.sum present | Also nested ⇒ never touched by CI Go gate. |

### Files, entry points, inter-package deps

```
cmd/huntx-engine/main.go            157 LOC  main() — subcommands: version|parse|benchmark|georoute|heal
cmd/huntx-engine/stream/parser.go    87      Record{unique_hash,raw_uri,protocol}; sha256[:8] hash; base64 accumulate+recurse
cmd/huntx-engine/internal/parse/     35      ParseReader/ParseFile wrappers over stream
cmd/huntx-engine/benchmark/         105      TCP dial worker-pool batch benchmarker
cmd/huntx-engine/georoute/          120      country inference (remark regex + TLD map), tiering, filter
cmd/huntx-engine/healing/           104      in-memory degraded-node daemon, backoff 5m/15m/1h/6h
cmd/huntx-engine/{huntx-engine.exe,main.exe}  4.5 MB each — COMMITTED TO GIT (git ls-files), 2 distinct SHA-256
cmd/huntx-tools/main.go             233      main() — runtime-generation{build,verify,validate-pointer}|release-manifest|verify-output|site-data
internal/outputverify/outputverify.go   169  Verify(dataDir): outputs→validate→stage→manifest→promote dist
internal/releasemanifest/releasemanifest.go 284  schema v1 artifact manifest (sha256/size/media type), TOCTOU-safe hashing
internal/runtimegen/runtimegen.go       421  generation manifest+pointer, canonical JSON, atomic writes w/ dir sync
internal/sitegen/sitegen.go             171  dist→docs/artifacts + catalog.json (schema v1), atomic promote w/ rollback
src/huntx/connectors/v2ray_collector/main.go 648  t.me/s/<ch> scraper (goquery), protocol regexes, IR filtering, port probes
```

Deps: `huntx-tools → internal/{outputverify,releasemanifest,runtimegen,sitegen}` (`cmd/huntx-tools/main.go:12-15`); `outputverify → releasemanifest`; `releasemanifest → runtimegen` (WriteBytesAtomic); `sitegen → releasemanifest + runtimegen`; `huntx-engine main → stream, internal/parse, benchmark, georoute, healing`. No cross-module imports.

### LIVE vs ORPHANED (evidence)

| Component | Status | Evidence |
|---|---|---|
| `cmd/huntx-tools` + all 4 `internal/` pkgs | **LIVE — production-critical** | Built in 4 huntx.yml jobs (`huntx.yml:122,187,338,616`) + `pr-validation.yml:79`; invoked at `huntx.yml:220,224,232,443,445,495,500,628,631` for state restore/verify, output verification, site generation, checkpoint build, S3 generation validation. |
| `cmd/huntx-engine/**` | **ORPHANED (rejected track)** | Zero references in any workflow/script/config (grep). Explicitly rejected: `docs/DONOR_PR_ABSORPTION_LEDGER.md:141` — "Standalone Go `huntx-engine` runtime and CLI \| Rejected with negative guardrail … defects in timeouts, accumulator bounds, input validation, no-op healing, and test contracts. HUNTX keeps one Python source of truth." Nested module ⇒ CI `go test -race ./...` never compiles it; `gofmt -l .` does scan it. Conductor marked the track "complete" (`a2736a8`) and committed the two `.exe`s. |
| `v2ray_collector/main.go` | **DORMANT (wired but unconfigured)** | Called via `subprocess.run(["go","run","main.go"], timeout=300)` from `src/huntx/connectors/v2ray_collector/connector.py:~65`; type allowed by config schema (`src/huntx/config/schema.py:106`), but `configs/config.prod.yaml` has **85 sources, all `telegram_user`** — no `v2ray_collector` source exists in production. |

---

## 2. Go capability catalog

| Capability | Inputs → Outputs | Algorithm / notable | Tests | Quality |
|---|---|---|---|---|
| **stream parse** (`stream/parser.go:42-87`) | reader/file → `[]Record` JSON | Line scan; `://` lines = records; non-URI lines accumulated into one base64 blob → decode → **recursive** ParseStream. Hash = hex(sha256(trim(uri))[:8]). | `parser_test.go` (43 L: raw, base64), `parse_test.go` (39 L) | Sound but **unbounded base64 accumulator** (`strings.Builder`, whole input) — the exact defect class cited in the ledger. Recursion depth unbounded for nested b64. |
| **benchmark** (`benchmark/benchmarker.go`) | `--targets host:port,…` → JSON `[]CheckResult{Target,Latency,Alive,Err}` | Buffered chan + N workers (default 50/100), `net.Dialer` TCP-only, per-target ctx timeout. | `benchmarker_test.go` (48 L) | OK; CLI wraps whole batch in `ctx = timeout*2` (`main.go:85`) regardless of target count → premature cancellation at scale. No TLS/HTTP probe despite usage text "TCP/TLS". |
| **georoute** (`georoute/engine.go`) | stdin stream + `--region ISO` → filtered JSON | Country from `#remark` regex `\b([A-Z]{2})\b` against 15-country whitelist, fallback TLD substring scan (15 TLDs), RWMutex cache; tier 1 = US/DE/NL/SG/JP; protocol normalization (ss/hy2/wg aliases). | `engine_test.go` (35 L) | Heuristic TLD `strings.Contains` (false positives possible); **drifted from Python twin** (15 vs 20 TLDs — missing `.se .fi .ch .it .es`). |
| **healing** (`healing/daemon.go`) | in-memory only | `RecordFailure` → backoff schedule idx; `Reinstate`, `GetDueForRetest`, `PurgeStale(48h)`. | `daemon_test.go` (36 L) | **No persistence** — state dies with process; CLI `heal` is a demo no-op (`main.go:130-136` records one fake failure). Ledger's "no-op healing" confirmed. |
| **outputverify** | `--data-dir` (default `persist/data`) → `dist/` promoted + Summary{files,total_size,protocols,formats,vmess_count} | Walk `outputs/` (symlinks forbidden), JSON-parse `.json`, zip-open `.zip`, base64-decode text and count 13 proxy schemes, stage to `.dist-stage-*`, build+verify release manifest, atomic dir promote w/ backup (`outputverify.go:147-169`). | **none** | High-quality hardening (symlink ban, empty-file rejection, atomic promote) but zero unit tests. |
| **releasemanifest** | root dir → `manifest.json` schema v1 | Per-artifact sha256+size+media type; `inspect()` re-stats before/after hashing to detect mid-hash mutation (`releasemanifest.go:228-251`); canonical path validation; `DisallowUnknownFields` + trailing-JSON rejection on read. | **none** | Excellent defensive design; untested in Go (Python twin is tested). |
| **runtimegen** | payload root + generation id → manifest + `current.json` pointer | Requires `state.db` present (`runtimegen.go:147-149`); full file-set equality on verify; canonical JSON for pointer digest; atomic writes (temp+fsync+rename+dir sync). | **none** | Core of the S3 immutability protocol; mirrors `scripts/runtime_generation.py` 1:1 (same regexes `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`, same schema). |
| **sitegen** | `dist/manifest.json` + docs dir → `docs/catalog.json` + `docs/artifacts/` | Re-verifies dist manifest, stages artifacts, builds catalog schema v1 (sizes, sha256, media type, tags=["release"]), two-phase atomic promote with rollback (`sitegen.go:110-137`). `--generated-at` RFC3339 override for reproducibility. | **none** | Clean; untested. |
| **v2ray_collector** | `telegram_channels.json` → `collected_configs.txt`, `ir_configs.txt`, `irb64.txt` | Scrapes `https://t.me/s/<ch>` HTML via goquery, 10-way concurrency, 11 protocol regexes, dedupe, Iranian-domain/Persian-char filter, TCP port probe "connectivity test" returning **fake 100 ms latency** (`main.go:152`). | none | Legacy-grade; emoji stdout; hardcoded heuristics; dormant in prod. |

**Test-coverage inversion (critical):** the 5 Go test files (201 LOC) all live in the ORPHANED nested module that CI never compiles; the LIVE `internal/` + `cmd/huntx-tools` code has **0 `_test.go` files**. CI's `go test -race ./...` (huntx.yml:119, pr-validation.yml:77) therefore exercises only dead code. (Protocol correctness is partially covered by Python twins: `tests/test_runtime_generation.py`, `tests/test_release_governance.py`.)

---

## 3. CI/CD map

### Trigger matrix

| Workflow (file, lines) | Triggers | Top-level permissions | Concurrency |
|---|---|---|---|
| `huntx.yml` (699) "huntx-production" | `schedule: 0 */2 * * *`; `workflow_dispatch` (max_workers 1-16, msg/file fresh/subsequent hours, `reset` bool + `reset_confirm` string) | `contents: read` | `huntx-production`, cancel-in-progress: **false** (queue, don't cancel) |
| `publish-generated-outputs.yml` (313) | `workflow_run(huntx-production completed)`; `push: main` on 4 control-plane paths (itself, inventory txt, 2 scripts); `workflow_dispatch(source_run_id, attempt)` | `actions: read, contents: write` | `publish-generated-outputs`, no cancel |
| `pr-validation.yml` (105) | `pull_request` + `push: fix/**, agent/**, codex/**` (path-filtered to workflows/configs/docs/go/cmd/internal/pyproject/requirements/scripts/src/tests) + dispatch | `contents: read` | per-PR, cancel-in-progress: true |
| `huntx-real-investigation-gate.yml` (49) | `workflow_run(huntx-production completed)` unless cancelled; dispatch | `actions: read, contents: read` | none |
| `huntx-telegram-activity-gate.yml` (37) | `workflow_run(huntx-production completed)` on success only | `actions: read, contents: read` | none |
| `dependabot.yml` | weekly Mon 05:00/05:30 Europe/Helsinki, github-actions + pip, grouped, 5 PR limit each | — | — |

### huntx.yml job graph

```
validate (production-quality-gate, 25m, ubuntu-24.04)
  gofmt -l / go test -race / go vet / build huntx-tools
  pip --require-hashes / compileall / flake8 / mypy / pytest -m "not perf" --strict-config --strict-markers
    └─► restore (restore-verified-state, 20m, environment: production, id-token: write)
          OIDC configure-aws-credentials (if AWS_ROLE_ARN set) + static AWS keys in env
          huntx-tools runtime-generation validate-pointer (current.json → manifest → payload)
          aws s3 sync generations/<gen>/payload → state-input; verify; reset path backs up pointer first
          upload artifact runtime-state-input-…
            └─► run (ingest-build-package, 115m, contents: read only, NO secrets except Telegram ones)
                  download state → safety-net snapshot of outputs/outputs_dev/state.db
                  timeout --signal=TERM --kill-after=60s 105m huntx … run   (line 413)
                  package: huntx-tools verify-output + site-data → docs/  (safety-net fallback if current fails)
                  checkpoint: scripts/checkpoint_runtime_state.py + huntx-tools runtime-generation build/verify
                  diagnostics: scripts/report_runtime_health.py → disposition output
                  uploads: runtime-checkpoint-…, huntx-output-…, huntx-logs-…, Pages artifact
                  "Enforce only truly fatal runtime outcomes" gate (lines 553-585)
                    ├─► persist (persist-immutable-state, 30m, if checkpoint_ready, environment: production, id-token: write)
                    │     reverify pointer+manifest → s3 sync payload → cp manifest → cmp remote → cp current.json LAST
                    └─► deploy-pages (25m, if run success && package_ready, pages: write + id-token: write,
                                       environment: github-pages) configure-pages → deploy-pages
```

Follow-ups on `workflow_run(huntx-production)`: publish-generated-outputs (see §4) + both gates.

### Pinned action SHAs (huntx.yml / pr-validation / publish)

checkout `3d3c42e5…` v7.0.1 · setup-go `b7ad1dad…` v7.0.0 · setup-python `5fda3b95…` v7.0.0 · upload-artifact `043fb46d…` v7.0.1 · download-artifact `3e5f45b2…` v8.0.1 · configure-aws-credentials `e6de0542…` v6.2.3 · upload-pages-artifact `fc324d35…` v5.0.0 · configure-pages `45bfe019…` v6.0.0 · deploy-pages `cd2ce8fc…` v5.0.0 · github-script `3a2844b7…` v9.0.0 (publish only).
**Exception:** both gate workflows use **unpinned `actions/github-script@v9`** (tag, mutable).

### Secrets usage

- `run` job (unprivileged otherwise): `TELEGRAM_TOKEN, PUBLISH_BOT_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_USER_SESSION` (`huntx.yml:404-408`).
- `restore`/`persist` only: `AWS_ROLE_ARN` (OIDC, `environment: production` protected), `S3_BUCKET, AWS_REGION`, plus **static** `AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY` fallback in the same steps (`huntx.yml:200-202, 646-648`).
- PR validation: `contents: read`, no secrets, no cloud creds — matches convergence invariant #46.
- Contract tests pin all of this textually: `tests/test_workflow_resilience.py` (asserts the 4 setup-go SHAs, timeout literals, upload order payload<manifest<pointer, `id-token: write` count, job names).

### Gates

Both `workflow_run` gates are **theater**: they only assert the `huntx-logs-*` artifact *exists* (`huntx-real-investigation-gate.yml:31-41`, `huntx-telegram-activity-gate.yml:23-37`); the "Enforce investigation contract" step is three `echo` lines (real-investigation-gate:43-49). Neither downloads/inspects `run-summary.json` metrics (`sources_checked, messages_scanned…`) they claim to require. Neither has `timeout-minutes` (defaults to 360). No test references them.

---

## 4. The outputs publication story, end-to-end

1. **Produce** — `huntx run` writes `persist/data/outputs/` (per-run artifacts: `all_sources.npvt{,.b64sub,.decoded.json,.singbox.json}`, `.opaque_bundle`, underscore variants) and `persist/data/outputs_dev/` (cumulative `_manifest.json` URI→first_seen).
2. **Verify + package** (`huntx.yml:430-475`, always runs) — requires ≥1 non-empty file in outputs → `.bin/huntx-tools verify-output` (Go: validates every artifact, builds `dist/` + `manifest.json`) → `huntx-tools site-data` renders `docs/catalog.json` + `docs/artifacts/`. If the fresh output fails verification, **safety-net restores the previous run's outputs** (snapshotted at lines 362-375) and publishes those (`source=restored`, "Release safenet activated").
3. **Deploy** — `upload-pages-artifact(docs/)` + `deploy-pages` job → GitHub Pages (GatherX artifact site, `docs/index.html` Preact/Tailwind SPA reading `catalog.json`). This satisfies the "artifact/Pages deployment" half of the convergence policy.
4. **Checkpoint** — `scripts/checkpoint_runtime_state.py` repairs SQLite (release leased work items → rewind ingestion windows whose raw blob is missing → delete orphan pending `seen_files` → reset legacy `source_state` → `wal_checkpoint(TRUNCATE)` + `quick_check`), then Go `runtime-generation build/verify` seals `state.db + raw/archive/outputs/outputs_dev/state` into an immutable generation; uploaded as `runtime-checkpoint-…` (1-day retention) alongside `huntx-output-…` (dist, 7d) and `huntx-logs-…` (7d).
5. **Persist to S3** (optional) — payload → manifest → remote `cmp` → `current.json` advanced **last** (pointer-last publication; order asserted by test).
6. **Publish to git** — `publish-generated-outputs.yml` on `workflow_run` success:
   - validates producer identity via github-script (`run.path == .github/workflows/huntx.yml`, `name == huntx-production`, `head_branch == main`, conclusion success, attempt match — lines 96-123);
   - downloads the 3 artifacts of that exact run;
   - `scripts/assemble_generated_snapshot.py` merges **previous `generated-outputs` branch `_manifest.json` + legacy main `outputs_dev/` recovery + current run manifest** into a cumulative snapshot (schema v3 `publication.json`, `SHA256SUMS`, `main-sync-files.txt` inventory);
   - pushes snapshot to branch **`generated-outputs`** with CAS on restored SHA (`--force-with-lease`, lines 223-254) — commit msg "Publish HUNTX outputs from run …";
   - then **mirrors `outputs/` + `outputs_dev/` into `main`** via `scripts/sync_generated_outputs_to_main.py`, scoped strictly to `.github/huntx-generated-files.txt` (12 paths), 3 retry attempts on non-fast-forward, **never force** (lines 256-295) — commit msg "Update HUNTX outputs from run …".

**Reconciling the tension:** `docs/history/CONVERGENCE_2026-07-27.md` (issue #46) declares "Generated output is an artifact/Pages deployment, **never a commit to `main`**." The later `docs/GENERATED_OUTPUTS_MODEL.md` ("Publication targets") explicitly *re-authorizes* a main mirror: "main/outputs/ and main/outputs_dev/, a source-branch mirror for users who browse the default branch", ownership-scoped by the inventory. Git history confirms ~2h cadence ("Update HUNTX outputs from run …" at 04:38, 06:42, 08:33, 10:28, 12:41, 14:27, 16:27, 18:30 UTC on 2026-08-16), introduced through PR #75 (`da7b97f`, the "next-gen-architecture-and-hardening" merge). **Verdict: deliberate, documented, tested policy drift — the convergence doc is stale on this single invariant; the publication model doc + `tests/test_generated_output_workflow_contract.py` are the current authority.** Residual risk: ~113 MB of cumulative proxy data rewritten on main every ~2 h grows git history without bound (`outputs_dev/_manifest.json` 25 MB, `proxies.json` 32 MB, `proxies.txt` 24 MB, `proxies_b64sub.txt` 32 MB).

---

## 5. scripts/ catalog

| Script (lines) | Purpose | Caller | Live/Dead | Notable logic |
|---|---|---|---|---|
| `assemble_generated_snapshot.py` (453) | Build verified cumulative publication snapshot | publish-generated-outputs.yml:198 | **LIVE** | Remark-stripping canonical identity (`strip_proxy_remark` re-serializes vmess JSON sorted); earliest-`first_seen` merge; **legacy bootstrap** recovers identities from `proxies.txt/.json/_b64sub` when `_manifest.json` is blank (sentinel ts=0; fail-closed if non-empty but unrecoverable, lines 182-238); writes `publication.json` schema 3, `main-sync-files.txt`, snapshot `SHA256SUMS`. |
| `build_release_manifest.py` (25) | Build+verify `dist/manifest.json` | none (grep) | **DEAD in CI** — superseded by Go `huntx-tools release-manifest` | Thin wrapper over `huntx.store.release_manifest`. Dev/local only. |
| `checkpoint_runtime_state.py` (157) | DB repair + checkpoint before packaging | huntx.yml:483 | **LIVE** | See §4.4; tested (`tests/test_checkpoint_runtime_state.py`). Conservative repair: rewinds windows instead of dropping data; refuses publish if pending rows still miss blobs. |
| `generate_site_data.py` (93) | dist → docs/catalog.json | none | **DEAD in CI** — superseded by Go `huntx-tools site-data` | Python twin of sitegen; older (no atomic staging). |
| `make_telethon_session.py` (30) | Interactive Telethon StringSession login → prints SESSION_STRING for the `TELEGRAM_USER_SESSION` secret | operator, manually | **LIVE (bootstrap)** | The only documented path to create the user-session secret consumed by `hardened_main.py` session lock. |
| `report_runtime_health.py` (225) | Render run-summary.json → annotations, diagnostics block, step summary, `disposition` output | huntx.yml:510 | **LIVE** | Disposition ∈ {success, degraded, fatal}; fallback: exit 0 w/o report → degraded; 124/137/143 + checkpoint → degraded; bounded 200-item inventory; 20 whitelisted metric keys. |
| `runtime_generation.py` (196) | Python reference impl of generation manifest/pointer protocol | none in CI (Go used) | **DEAD in CI but TESTED** (`tests/test_runtime_generation.py`) | Same schema/regexes as Go `internal/runtimegen`; docstring: "deliberately contains no network code so the integrity protocol is deterministic and unit-testable." |
| `sync_generated_outputs_to_main.py` (158) | Inventory-scoped mirror of snapshot → main worktree | publish-generated-outputs.yml:267 | **LIVE** | Only paths under `outputs/`, `outputs_dev/` allowed; refuses symlinks both directions; deletes stale managed files; atomic inventory replace; prunes empty dirs. Tested (`test_generated_output_sync_retry.py`). |
| `verify_output.py` (274) | Rich dev verifier: text/zip/json/b64 validation, vmess→V2Ray outbound conversion, generates `v2ray_test_config.json`, copies itself into dist | none directly; publish workflow asserts its presence (`test -f scripts/verify_output.py`, publish yml:274) and dist self-copy ships in outputs | **SEMI-LIVE (contract artifact)** | Imports `huntx.core.router._PROXY_SCHEMES` (private import); rmtree guard on `dist` (name+depth check, lines 204-211). |
| `__init__.py` | package marker so `from scripts.x import …` works in tests | — | LIVE | |

---

## 6. systemd/

Single file `scripts/systemd/mergebot.service` (14 lines): `Type=simple`, `User=mergebot`, `WorkingDirectory=/opt/mergebot`, `ExecStart=/opt/mergebot/.venv/bin/mergebot --config /opt/mergebot/configs/config.prod.yaml run`, `Restart=always`, `RestartSec=60`. **Legacy pre-rename artifact** — binary was `mergebot`, now `huntx` (`pyproject.toml:31`); no `huntx.service` exists. Implied model: long-running daemon on a VM. Contradicts the actual production model (cron-driven ephemeral GitHub Actions runners) — dead config, but preserves the intended self-hosted deployment shape (venv + prod config + always-restart) for a future VM deployment. The CE handoff (`docs/handoffs/ce_handoff_huntx_optimization.md:42`) lists "systemd unit files for production deployment packaging" as a recommended next step.

---

## 7. Defects & risks

| # | Severity | Finding |
|---|---|---|
| 1 | **HIGH** | **Committed binaries**: `cmd/huntx-engine/huntx-engine.exe` + `main.exe` (2×4.5 MB, distinct SHA-256) are git-tracked artifacts of an orphaned, rejected module. Repo bloat + unauditable binary supply chain. |
| 2 | **HIGH** | **Inverted Go test coverage**: CI `go test -race ./...` runs only the orphaned `huntx-engine` tests (nested module — actually *excluded* from root `./...`, so effectively **zero** Go tests execute); the production LIVE `internal/`+`huntx-tools` (~1,278 LOC) has no tests. Correctness rides on Python twins + workflow contract tests. |
| 3 | **HIGH** | **Toolchain drift**: `cmd/huntx-engine/go.mod` demands `go 1.26`; CI installs Go from root `go.mod` (1.23.1). The engine cannot build in CI today; `gofmt -l .` still gates on its formatting. Silent divergence between the two Go surfaces. |
| 4 | **MED** | **Cron overlap/queueing**: 2 h cron vs 115 m run-job + ~25 m publish job, `cancel-in-progress: false` → overlapping runs queue rather than cancel; a slow run can delay the next generation; publish concurrency group is separate from production group. |
| 5 | **MED** | **Gate workflows are non-enforcing** (artifact-existence only, echo "contract"), use **unpinned `actions/github-script@v9`** (only mutable refs in the repo), and have **no `timeout-minutes`**. False sense of oversight. |
| 6 | **MED** | **Dual AWS credential paths**: OIDC role assumption and static `AWS_ACCESS_KEY_ID/SECRET` coexist in restore/persist steps (`huntx.yml:189-202, 636-648`). Static keys broaden the blast radius the OIDC-only design intended to minimize. |
| 7 | **MED** | **Unbounded main-branch growth**: ~113 MB of generated data committed every ~2 h (12 commits/day); no LFS, no retention strategy; `publish` checks out `fetch-depth: 0`. |
| 8 | **MED** | **Policy drift**: convergence doc's "never a commit to main" invariant contradicted by the sanctioned main mirror (§4); stale doc can mislead future governance reviews. |
| 9 | **LOW** | `docs/catalog.json` is stale legacy (2026-02-16, old schema with `type/ext/last_modified`) vs sitegen schema v1 — committed docs copy diverges from per-run generated catalog. |
| 10 | **LOW** | v2ray_collector: runtime `go run main.go` needs live module download (no vendor); fake 100 ms latency constant; emoji/printf logging; dormant but one config line away from production. |
| 11 | **LOW** | huntx-engine latent defects (if ever revived): unbounded b64 accumulator, `heal` no-op demo, batch ctx = 2× per-target timeout, 15-vs-20 TLD drift, in-memory-only healing. |
| 12 | **LOW** | `pr-validation` push trigger covers only `fix/**, agent/**, codex/**`; direct pushes to `main` get no PR-style gate (only the cron validate job). |
| 13 | **INFO** | `requirements.txt` is pip-compile hashed (340 hashes) and installed `--require-hashes` — strong supply chain; dev tools pinned inline in pr-validation but unpinned in `requirements-dev.in`. No Makefile/justfile — all automation lives in workflows. |

---

## 8. Duplication — Go vs Python, canonicality & consolidation

| Domain | Go impl | Python impl | Canonical | Direction |
|---|---|---|---|---|
| Stream/subscription parsing | `huntx-engine/stream` (+`internal/parse`) | `src/huntx/formats/*` (12 handlers), `proxy_uri_validator.py`, `formats/common/singbox.py:parse_proxy_uri` | **Python** (tested, production) | Archive Go; ledger already decided ("one Python source of truth"). |
| Geo routing | `georoute` (15 TLDs, in-mem cache) | `core/geo_routing.py` (20 TLDs, `lru_cache`, taxonomy, tested `test_geo_routing.py`) | **Python** | Archive Go; port nothing back (Go is a strict subset). |
| Self-healing | `healing` (in-memory) | `core/self_healing.py` `SelfHealingDaemon` (SQLite-durable, **identical backoff 300/900/3600/21600 s**, tested `test_self_healing.py`) | **Python** | Archive Go (durability wins). |
| Latency benchmarking | `benchmark` (sync TCP pool) | `core/latency_benchmarker.py` (async, URI-aware, tested `test_latency_benchmarker.py`) | **Python** | Archive Go. |
| Runtime generation protocol | `internal/runtimegen` + `huntx-tools` CLI — **LIVE in CI** | `scripts/runtime_generation.py` — tested reference | **Go executes, Python specifies/tests** | Keep both intentionally (Python = unit-testable spec; Go = CI binary). If Go test coverage is ever required, port `tests/test_runtime_generation.py` cases to Go. |
| Release manifest | `internal/releasemanifest` — LIVE | `huntx/store/release_manifest.py` (used by dead scripts + `test_release_governance.py`) | **Go executes** | Same dual-track rationale; keep Python as spec/tests. |
| Output verification | `internal/outputverify` — LIVE | `scripts/verify_output.py` (richer reporting, v2ray config gen) | **Go for gate**, Python for dev UX | Keep; consider porting `v2ray_test_config.json` generation if still wanted. |
| Site/catalog generation | `internal/sitegen` — LIVE | `scripts/generate_site_data.py` (dead twin) | **Go** | Delete/absorb Python twin. |
| Telegram scraping | `v2ray_collector/main.go` | Python connectors (telegram/telegram_user) | Python pipeline | Dormant; if revived, vendor deps + real latency measurement, or rewrite as Python connector. |

**Consolidation verdict:** Python is canonical for all pipeline logic (per ledger + test investment). Go's justified footprint is exactly `cmd/huntx-tools` + `internal/*` — the release/integrity plane — which should get native Go tests. `cmd/huntx-engine` (+ `.exe`s) is archive material; its only salvageable idea (modular parse library) already exists in Python.

---

## 9. Knowledge preservation (operational know-how embedded here)

1. **Layered watchdog** (`huntx.yml:55-58,413` + `hardened_main.py:100`): internal run budget `HUNTX_RUN_TIMEOUT=5400s` (90 m, default 12600) < external `timeout --signal=TERM 105m` < `--kill-after=60s` < job `timeout-minutes: 115` < cron 120 m. TERM gives the orchestrator a graceful-cancel window; exit codes 124/137/143 are treated as *recoverable* iff a verified checkpoint exists (`huntx.yml:577-582`).
2. **Degraded-success semantics**: `report_runtime_health.py` maps structured `run-summary.json` dispositions (success/degraded/fatal) + fallbacks; the enforcement step fails only on fatal disposition or missing checkpoint — a degraded run with a good checkpoint reports success and publishes the safety-net output.
3. **Immutable generation protocol**: upload payload → upload manifest → download-and-`cmp` manifest → advance `current.json` pointer **last**; restore validates pointer→manifest→payload before use; reset backs up the pointer to `backups/<stamp>/current.json` and verifies with `head-object` before wiping; reset requires literal `RESET-HUNTX-STATE`.
4. **Checkpoint repair contract**: leased work items → `partial`; pending observations missing content-addressed raw blobs → window rewound (`last_error='rewound: …'`) or legacy source reset; WAL truncated; `quick_check` must pass; re-verification after repair refuses publication on residual gaps.
5. **Safety-net publication**: previous verified outputs are snapshotted pre-run and republished when the fresh output fails independent verification — "publish last good, keep new state".
6. **Cumulative-identity preservation**: rendered legacy history (`proxies.txt/.json/_b64sub`) is authoritative migration input; manifest merge keeps earliest `first_seen`; unrecoverable non-empty legacy fails closed; vmess remarks are canonicalized before identity comparison.
7. **Main-mirror safety**: inventory-scoped writes (`.github/huntx-generated-files.txt`), symlink refusal, no force-push to main, `--force-with-lease` + remote-SHA CAS on the generated branch, 3-attempt non-FF retry.
8. **Session bootstrap**: `make_telethon_session.py` → `TELEGRAM_USER_SESSION` secret → per-session file lock in `hardened_main.py` (session-lease path) preventing concurrent MTProto sessions.
9. **Workflow-as-tested-code**: `tests/test_workflow_resilience.py` + `test_generated_output_*` pin action SHAs, timeout literals, step ordering, and permission boundaries as pytest assertions — a reusable pattern for CI regression protection.
10. **Reproducible builds**: `PYTHONHASHSEED=0`, `--generated-at` RFC3339 override in sitegen, deterministic sorted walks everywhere, `pip --require-hashes`.

---

## Appendix — build/config plumbing

- `pyproject.toml`: huntx 0.2.0, `requires-python >=3.11`, entry `huntx = huntx.cli.hardened_main:main` (:31); deps PyYAML/telethon<2/pydantic≥2/pyaes/rsa/pyasn1/cryptography (with security note on rsa/pyaes pinning, :6-8); pytest `asyncio_mode=auto`, `perf` marker; mypy overrides for `huntx.bot.{delivery,interactive}`; explicit note that flake8 config lives only in `.flake8` (:63-65).
- `requirements.txt`: pip-compile `--generate-hashes` from pyproject (340 hash lines); CI installs with `--require-hashes`.
- `requirements-dev.in`: `-r requirements.txt` + unpinned flake8/mypy/pytest/types-*; pr-validation pins exact dev versions inline.
- No Makefile/justfile — workflows are the only task runners.
- `.gitignore` reveals runtime layout: `persist/`, `data/`, `*.db`, `temp_*`, `*.session`, `huntx-output/`, `.tmp/` (module cache), `src/huntx/connectors/v2ray_collector/*.txt` (scraper outputs), agent-index dirs. **Not ignored**: `outputs/`, `outputs_dev/` (deliberate — main mirror), `cmd/huntx-engine/*.exe` (defect #1).
- `configs/config.prod.yaml`: 85 `telegram_user` sources (numeric peer IDs), YAML anchors for `include_formats: [all]`, single route `all_sources` fanning all sources; `${TELEGRAM_API_ID/API_HASH/USER_SESSION}` env expansion.
