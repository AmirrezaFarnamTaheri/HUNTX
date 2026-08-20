# HUNTX Repository-Wide Refinement — 2026-08-19

## Purpose

This document records the evidence boundary, repository coverage, corrections, validation, and remaining non-claims for the whole-repository refinement pass requested on 2026-08-19.

It is intentionally a present-state engineering record, not a generic improvement backlog.

## Pinned source state

Primary anchor supplied by the operator:

- archive: `Huntx-lite.zip`
- exact recorded Git revision: `2939cc3cae71353133390e022211f822d2a8c49a`
- unpacked anchor corpus: 329 files across 59 directories, approximately 6.27 MB

Remote source of truth at start of refinement:

- repository: `AmirrezaFarnamTaheri/HUNTX`
- branch: `main`
- exact head: `adb02313ca6aeaec3af881b3186bb19387dbcba7`
- relation: remote `main` was 157 commits ahead of the anchor and 0 behind; the anchor is an ancestor, not a divergent fork.

Implementation branch:

- `feat/repository-wide-refinement-2026-08-19`
- draft PR: #77

The ZIP was used as the full-corpus anchor. Files changed between the anchor revision and current `main` were reconciled against remote source before conclusions or edits were made.

## Coverage model

Every path in the supplied archive was inventoried and classified before repository-wide conclusions were made. Coverage was deliberately different by artifact class:

| Class | Treatment |
|---|---|
| Python/Go runtime source | Direct static inspection, call/reachability tracing, contradiction search, targeted regression analysis |
| Tests | Direct inspection where they reveal runtime contracts; suite-wide CI execution used as regression oracle |
| Scripts/automation | Direct inspection for state mutation, path safety, destructive behavior, subprocess/network use, and deployment role |
| Workflow/config/manifests | Direct inspection for runtime/deployment truth, permissions, pinning, state handoff, validation and failure behavior |
| Documentation/conductor/forensic reports | Used as historical/intent evidence, then checked against implementation; stale claims reconciled rather than trusted |
| Generated `outputs/` / `outputs_dev/` | Classified as generated publication artifacts, not promoted to architecture/source components |
| Historical snapshots/data | Classified as historical/generated material; inspected for live references before cleanup decisions |

Anchor classification summary:

- runtime source: 73 files / 337,123 bytes
- tests: 142 files / 1,035,205 bytes
- automation/scripts: 23 files / 360,233 bytes
- build/config/operations: 15 files / 544,859 bytes
- docs/history: 27 files / 433,943 bytes
- generated artifacts: 24 files / 2,679,580 bytes
- prototypes: 2 files / 28,823 bytes
- other: 1 file

The anchor contained roughly 7,230 runtime Python LOC, 23,852 test Python LOC, 4,476 automation Python LOC, and 729 prototype Python LOC.

Corpus-wide mechanical checks additionally searched executable code for placeholders, unsafe evaluation/execution, shell-enabled subprocesses, bare exceptions, unverified TLS contexts, direct SQLite/open-file lifecycle patterns, task creation, subprocess use, and broad exception boundaries. No executable `TODO`/`FIXME` placeholders, `eval`, `exec`, `os.system`, `shell=True` subprocesses, bare `except`, or explicit TLS-verification bypass were found in the inspected executable corpus. Broad exception handlers were individually triaged where they were silent or crossed material boundaries.

## Implemented corrections

### RW-01 — Consolidated governed run entrypoints

**Problem**

Multiple callable CLI/operator paths could construct or reach different orchestration graphs. The installed console wrapper had hardened behavior, while direct `huntx.cli.main`, the compatibility `cli.commands.run` helper, and bot-admin execution retained duplicated or legacy construction logic.

**Correction**

Added `huntx.cli.run_service` as the shared operator-facing execution boundary. It owns configuration load/validation, worker/timeout/fetch-window validation, runtime-state locking, MTProto session fencing, `create_production_orchestrator()` construction, partial-export/no-publish execution options, and structured health evaluation/emission.

`hardened_main` is now a path/default wrapper rather than an import-time monkey patch. CLI, compatibility helper, and GatherX admin runs all delegate to the same service.

**Strategic value:** High-Leverage

### RW-02 — Host/user-wide MTProto session fencing

**Problem**

The old session-lock path lived beneath each runtime state directory. Two HUNTX invocations using the same Telethon session but different `--data-dir` values therefore did not fence one another.

**Correction**

All configured MTProto session identities are extracted from validated config, deduplicated, sorted, and locked in a host/user-wide namespace independent of runtime data paths. `HUNTX_SESSION_LOCK_DIR` provides an explicit operator override. Sorted acquisition prevents multi-session deadlock.

A later adversarial pass also found that ordinary OS process locks must not reuse the durable `session_lease_path()` namespace, because durable session leases use file existence, heartbeat, and stale-reaping semantics rather than advisory-lock semantics. Process locks now use a separate `process-locks/` namespace with the same one-way session digest; durable `session-leases/` files remain exclusively owned by the lease protocol.

**Strategic value:** High-Leverage

### RW-03 — Lock wrapper no longer masks downstream failures

**Problem**

`acquire_lock()` caught `OSError` around the caller's yielded body. A real downstream filesystem/network `OSError` could therefore be rewritten as `Another instance of HuntX is already running.`

**Correction**

Only acquisition failures are translated. Protected-operation exceptions propagate unchanged; release is best-effort in `finally`.

### RW-04 — Async circuit-breaker state made concurrency-safe

**Problem**

The helper circuit breaker had mutable state without synchronization and could admit multiple recovery probes or preserve stale failure counts. A cancelled HALF_OPEN recovery probe could also retain exclusive-probe ownership indefinitely.

**Correction**

Added validated configuration, an async state lock, exactly-one HALF_OPEN probe semantics, fail-fast concurrent callers, consecutive-failure reset on success, deterministic reopen/close transitions, and cancellation/abnormal-exit cleanup that reopens the breaker and releases probe ownership.

### RW-05 — Self-healing state lifecycle hardened

**Problem**

The helper accepted empty/nonpositive retry schedules, nonfinite time values, and unsafe purge ages; its shared in-memory SQLite connection was usable across threads without serialization.

**Correction**

Validated positive schedules, finite time, fail-safe nonpositive purge no-op, serialized SQLite access, explicit close/context-manager lifecycle, deterministic due ordering, and input validation.

### RW-06 — Proxy scoring/geo helpers fail safely on malformed telemetry

**Problem**

NaN/type-invalid metrics could poison ranking and lexical URI splitting could mis-handle IPv6/malformed hosts.

**Correction**

Scores now coerce to finite bounded metrics and return 0..100. Geo routing structurally uses URL parsing, safely handles malformed/byte-backed records, and does not invent IP geolocation.

### RW-07 — Destructive prune retention is fail-closed

**Problem**

`prune_old_data(0)` was reachable from multiple callers and could delete essentially all eligible historical state older than the current instant.

**Correction**

The repository-level hardening contract now rejects zero, negative, boolean, fractional, and string retention values before any destructive SQL executes. CLI/admin callers inherit the same invariant.

### RW-08 — Raw-blob builder/enrichment contract repaired

**Problem**

Several handlers inherit `OpaqueBundleHandler.build()` (which requires `data.blob_hash`) but their successful deep-parse branches replaced the canonical raw record with enrichment-only data. A successfully decrypted record could therefore become unbuildable. TUT/SKS/TMT were also absent from the raw-blob retention set.

Affected handlers:

- TUT
- SKS
- TMT
- NPV4
- HAT

**Correction**

Raw source SHA-256, filename, size, and `blob_hash` remain canonical. Decryption/HAPP inspection is metadata enrichment only. TUT/SKS/TMT are added to raw-blob retention protection. Regression tests build ZIPs back from enriched records and assert byte equivalence.

### RW-09 — `npvtsub` now shares proxy admission with `npvt`

**Problem**

`npvt` used protocol-aware URI validation while `npvtsub` could accept recognized prefixes without the same validation, allowing malformed subscriptions into persistence/build.

**Correction**

`NpvtSubHandler` inherits the canonical `NpvtHandler` parser/build contract. Validation, canonicalization, base64 handling, authenticated HTTP-proxy handling, and deduplication now have one owner.

### RW-10 — Reject forensic evidence cannot silently overwrite

**Problem**

Reject filenames were second-resolution `(source, reason)` coordinates; multiple rejects in the same second could overwrite evidence.

**Correction**

Names now include UTC microseconds, process identity, sanitized source/reason, payload digest, and a collision fallback. Payloads are bytes-only and writes remain atomic.

### RW-11 — Traceback credential redaction

**Problem**

The logging filter redacted `record.getMessage()`, but Python appends exception traceback text later during formatting. A secret embedded in an exception message could therefore bypass the filter.

**Correction**

A final redacting formatter sanitizes the fully rendered message, including exception/stack text, while retaining the early filter as defense in depth.

### RW-12 — Repository ballast/stale deployment surface removed

Removed from the live branch after reachability checks:

- tracked `data_archive/` generated historical snapshot tree;
- obsolete `scripts/systemd/mergebot.service` referencing a non-HUNTX `/opt/mergebot` executable/path.

`data_archive/` is ignored to prevent accidental reintroduction. Generated product mirrors in `outputs/` and `outputs_dev/` remain because the current publication workflow intentionally owns them.

### RW-13 — Documentation reconciled to implementation

Replaced stale current-state claims in:

- `README.md`
- `docs/USER_GUIDE.md`
- `docs/DEVELOPMENT.md`
- `conductor/tech-stack.md`
- `conductor/product.md`
- `conductor/workflow.md`
- `conductor/product-guidelines.md`
- `conductor/tracks.md`

Historical audit ledgers are not rewritten retroactively; they receive a present-state reconciliation notice.

Corrections include five current CLI commands, admin-only bot controls, current format/buildability distinctions, 85-source current production config, governed LIFO MTProto production ingestion, current output/storage paths, immutable S3 generation protocol, generated-output mirror behavior, and production versus implemented-but-inactive components.

### RW-14 — Derived outputs can no longer masquerade as route inputs

**Problem**

Configuration validation accepted derivative IDs such as `b64sub`, `npvt.decoded.json`, and `npvt.singbox.json` as route formats, but the build pipeline creates these only as derivatives of configured `npvt`/`npvtsub` base formats. A configuration could therefore validate yet have no independently buildable record type/handler for the requested derivative.

**Correction**

`validate_config()` now rejects direct derivative route inputs and directs operators to configure `npvt` and/or `npvtsub`, which automatically emit supported derivatives. Parse-only route formats remain independently rejected.

### RW-15 — Latency filtering has bounded task fan-out

**Problem**

`filter_proxies_by_latency()` used a semaphore around probes but still constructed one coroutine/task per input proxy. Socket concurrency was bounded; scheduler/memory fan-out was not.

**Correction**

The helper now validates finite positive thresholds/timeouts, validates concurrency in a fixed 1..1000 range, uses a fixed worker set, and preserves successful results in input order. Existing public-address validation remains intact.

### RW-16 — Clean/reset own the real artifact storage surfaces

**Problem**

`ArtifactStore` persists current internal output under `data/dist/` and changed-output history under `data/archive/`, while legacy CLI clean/reset inventories targeted `data/artifacts/` but omitted those live directories. A claimed factory reset could therefore leave generated/internal artifacts behind.

**Correction**

Maintenance commands now live in `huntx.cli.commands.maintenance` with one deduplicated ownership inventory covering raw, legacy artifact path, live `dist/`, live `archive/`, rejects, logs, outputs, dev outputs, the database, and state directory. `cli.main` keeps compatibility aliases for previously imported backup/restore helpers while delegating maintenance behavior to the owned module.

### RW-17 — Destructive maintenance preserves users or fails before deletion

**Problem**

GatherX backup errors were previously logged and converted to `None`, making a failed backup indistinguishable from “no users/table.” Clean/reset could then proceed destructively. Reset could also continue after failure to create its full database backup, and partial deletion failures could interrupt before preserved users were restored.

**Correction**

Actual SQLite/IO backup failures now abort before deletion. Reset backup-copy failure is fatal before removal. Once preservation succeeds, deletion failures are accumulated; runtime directories/schema are recreated and GatherX users are restored before an explicit incomplete-maintenance error is raised.

### RW-18 — Stale regressions follow the real buildability contract

**Problem**

One legacy V2Ray-source regression fixture used `b64sub` merely as a convenient route format. After RW-14 correctly rejected derivative route inputs, this fixture failed for an unrelated reason.

**Correction**

The fixture now uses buildable `npvt`, preserving its actual purpose: prove `v2ray_collector` is a valid source type. CI therefore tests the new validator without weakening it to satisfy stale test setup.

## Inspected areas retained without material change

The refinement pass also directly inspected representative/high-risk implementations where no justified code change was made, including:

- checkpoint runtime-state verification and SQLite/raw integrity checks;
- generated-output synchronization path/symlink scope guards;
- release-manifest canonical path/digest validation;
- recursive ZIP/content-type bounds and zip-slip protections;
- source lifecycle trust-state validation;
- fail-closed environment placeholder expansion;
- typed environment tuning helpers;
- opaque-bundle resource ceilings/truncation behavior;
- source/governed build verdict paths;
- Bot API/MTProto download bounds and durable acknowledgement design;
- Go public-address probe protections introduced by earlier hardening;
- release/site-data compatibility wrapper scripts, with production authority retained by `huntx-tools`.

No change was made solely to create churn when the existing contract was supported by implementation/tests.

## Validation record

### Anchor baseline (local extracted archive)

The anchor itself was executable enough for structural checks but is intentionally not claimed as current:

- Python `compileall`: passed
- Go `go test -race ./...`: passed
- Go `go vet ./...`: passed
- anchor Go formatting: not clean (historical state; later main already repaired this)
- full Python test collection in the local anchor environment was blocked because Telethon was not installed there

### PR validation progression

PR run #674, head `7c4e667e3f52199236395472ce3c06cf42374bbf`:

- workflow YAML: passed
- Go format/race/vet/build: passed
- Python dependency/install/compile: passed
- Flake8: 0 findings
- MyPy: failed on two newly introduced typing defects before Pytest ran
  - dynamic raw-blob tuple assignment arity
  - overly broad timeout temporary type

Both defects were corrected without disabling or suppressing the type checker.

PR run #699, head `b989620cb359867c9f5ebbd070fc23cff12b0fb0`:

- workflow YAML: passed
- Go format/race/vet/build: passed
- Python dependency/install/compile: passed
- Flake8 failed on three maintenance-split unused imports before MyPy/Pytest ran

The stale `sys` import was removed and the two intentionally retained compatibility aliases were made explicit module exports rather than suppressing lint.

PR run #700, head `cfc5b30c215ecf47405b89b3d0a0404d7e0bbf2c`:

- workflow YAML: passed
- Go format/race/vet/build: passed
- Python dependency/install/compile: passed
- Flake8: 0 findings
- MyPy: success
- Pytest reached the full suite: 727 passed, 4 deselected, 57 subtests; one regression fixture failed because it configured derivative-only `b64sub` while testing V2Ray source acceptance

The stale fixture was corrected to use `npvt`. No validator relaxation was made.

A later adversarial review then separated process-level MTProto OS locks from durable session-lease files and added an explicit non-alias regression. A final exact-head validation run is required after this documentation reconciliation before PR readiness can be claimed.

## Explicit remaining gaps / non-claims

These are not repository bugs silently declared fixed by this pass.

### Canonical typed proxy IR

Records remain dictionary/format-oriented rather than one typed normalized proxy intermediate representation. This is a **transformational opportunity**, not required for the verified fixes above and not appropriate to introduce as an unproven repository-wide migration inside the same remediation branch.

### Native-client conformance gates

HUNTX validates syntax and safely narrows sing-box conversion, but this pass does not claim promoted artifacts have been imported/executed against every target native client. Native client gates remain separate release-engineering work.

### Supply-chain provenance / SBOM

Runtime requirements are hash-pinned, CI tooling is exact-version pinned, and GitHub actions are SHA-pinned. A complete signed SBOM/provenance/attestation pipeline is not established here.

### Full distributed tracing

Structured run health/investigation metrics exist. End-to-end trace IDs and complete span propagation do not.

### Branch protection

At the start of this pass GitHub reported `main` as unprotected with no required status checks. The available repository mutation tools for this session do not expose branch-protection configuration. This is an **external repository-setting action** and must not be claimed as fixed by code.

### Historical credential rotation

Repository fallback secrets were removed in earlier hardening. Any credential that was historically exposed must be revoked/rotated at its issuing provider. Git commits cannot prove or perform provider-side revocation.

## Completion gate for this refinement PR

Before changing the draft/readiness claim:

1. exact current head passes workflow YAML validation;
2. Go `gofmt`, race tests, vet, and both builds pass;
3. Python install/check/compile passes;
4. Flake8 reports zero findings;
5. MyPy reports no errors;
6. full non-performance Pytest suite passes;
7. new regression tests execute, not merely collect;
8. PR inline review threads have no unresolved actionable defects;
9. README/user/development docs match the final implementation;
10. PR body records exact head and actual validation results.

Merging is intentionally outside this pass unless the operator explicitly requests it.
