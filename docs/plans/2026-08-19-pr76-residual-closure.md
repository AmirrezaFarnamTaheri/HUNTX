# PR #76 Residual-Risk Closure

Date: 2026-08-19

This document closes the five explicit follow-up items left in the **Residual risks / follow-up** section of `2026-08-19-pr76-second-order-hardening.md`. That earlier section is retained as an audit snapshot of what remained at that point; this document supersedes its status for those five items.

## Closure status

All five repository-addressable residual items are now resolved in implementation and protected by regression tests.

### 1. Production CI QA-tool reproducibility — closed

Problem: PR validation pinned Flake8/MyPy/Pytest/type-stub versions while the scheduled production quality gate installed floating versions.

Resolution:

- added `requirements-ci.txt` as the shared, fully version-pinned CI quality-tool dependency set;
- PR validation and production validation both consume the same file;
- both workflows include it in the Python cache identity;
- duplicated inline QA-package version lists were removed;
- regression coverage verifies every active requirement line is exactly version-pinned and both workflows consume the shared source.

This removes silent PR-vs-production toolchain drift without mixing CI-only tooling into the runtime dependency lock.

### 2. Bot informational/access policy — closed

Problem: protected artifacts were approval-gated, but the remaining command surface did not have one explicit public/approved/admin classification.

Resolution:

- all GatherX commands are classified into disjoint policy sets:
  - **private/pending-safe:** `start`, `help`, `formats`, `protocols`, `myinfo`, `ping`;
  - **approved private user:** `get`, `latest`, `count`, `setformat`, `mute`, `unmute`;
  - **private administrator:** `status`, `admin`, `approve`, `deny`, `pending`;
- every class is private-chat-only; there is no supported group/channel command surface;
- protected callback actions are classified as well, not merely text commands;
- admin commands are not exposed in the default Telegram bot menu;
- pending-user settings UI does not expose download/delivery mutation buttons;
- `/status` is admin-only and `/count` is approval-gated;
- regression coverage proves pending, approved, admin and group behavior separately and verifies the policy sets are disjoint.

The policy is now declared rather than inherited from historical handler behavior.

### 3. Route-prefix/output ownership — closed structurally

Problem: stale-output cleanup inferred ownership from `filename.startswith(route)`, forcing configuration to reject otherwise valid route pairs such as `prod` and `production`.

Resolution:

- added exact output identity/ownership logic in `src/huntx/core/output_ownership.py`;
- generated filename ownership is represented by `.huntx-output-ownership.json` with exact `filename -> {route, format}` entries;
- stale cleanup may delete only files explicitly owned by the prior manifest;
- first-run migration adopts only exact currently configured route/format filenames, never prefixes;
- malformed/untrusted manifest names are rejected rather than used as filesystem paths;
- unrelated files are never inferred as route-owned;
- retention semantics are preserved for owned stale artifacts;
- exact configured/build-result filename collisions fail explicitly;
- the governed production runtime installs this exporter;
- the release verifier excludes the internal ownership manifest from `dist` while allowing it to persist with state;
- the former route-prefix configuration prohibition is removed, so `prod` and `production` can coexist safely;
- regression tests prove a stale `production.npvt` can be pruned without deleting `production_notes.txt` and that prefix-related route names validate.

### 4. Immediate source-trust revocation of active leases — closed

Problem: trust revocation terminalized pending/partial/retry work but deliberately left a currently leased queue item alive until its lease expired.

Resolution:

- `PersistentIngestionQueue.terminalize_source()` now includes `leased` rows;
- revocation atomically clears lease owner/token/expiry and marks all unfinished source work quarantined;
- a worker holding the now-invalid token cannot checkpoint the page;
- window page writes and the queue checkpoint share one SQLite transaction, so checkpoint failure rolls the page writes back;
- if a page transaction committed before revocation linearized, the existing current-trust build filter still prevents revoked-source data from publication;
- regression coverage explicitly inserts a probe row in the same transaction, revokes the lease, forces checkpoint failure, and verifies the probe write rolled back.

This removes the residual single-runner caveat for source revocation correctness.

### 5. Separate `cmd/huntx-engine` Go module/toolchain — closed

Problem: the engine remained a separate `go.mod`/Go 1.26 module even after CI began testing it, leaving a maintenance/toolchain boundary from the root Go 1.23.1 module.

Resolution:

- removed `cmd/huntx-engine/go.mod`;
- engine imports now use the repository root module path;
- the root `go test -race ./...` and `go vet ./...` naturally traverse the engine packages;
- PR and production quality gates use one `setup-go` based on the root `go.mod`;
- both gates build `./cmd/huntx-engine` explicitly;
- Go 1.23.1 CI has already executed the engine benchmark/georoute/healing/parser/stream tests successfully under the unified module;
- regression coverage asserts the nested module file is absent and the workflow no longer references a nested toolchain.

## Behavioral validation added

The closure is covered by `tests/test_residual_closure.py` plus updated existing tests and `internal/outputverify/outputverify_test.go`. Existing fixtures were updated to model the hardened contracts instead of bypassing them: direct-delivery tests create real approved private identities, bot command tests use real private sender/chat semantics, status is tested as an administrator, count as an approved user, telemetry fakes initialize their metric contract, and approval commands are expected to be registered through policy wrappers.

The code-only exact head immediately before this closure document passed PR validation run **#672** with:

- workflow YAML validation: passed;
- root Go 1.23.1 gate: `gofmt`, `go test -race ./...`, `go vet ./...`, `go build ./cmd/huntx-tools`, `go build ./cmd/huntx-engine`: passed;
- Flake8: `0` findings;
- MyPy: `Success: no issues found in 98 source files`;
- Pytest: **654 passed, 4 deselected, 57 subtests passed**.

A new PR validation run must pass on the documentation-inclusive final head before PR #76 is represented as fully closed.

## Scope boundary

This closure means the five explicit repository residuals from the second-order audit are no longer open implementation issues. It does **not** claim that repository changes can revoke any third-party credential that may have appeared in historical Git commits. Any historically exposed external credential must be rotated/revoked at its issuing service; current-tree secret removal and history documentation cannot invalidate a credential outside GitHub.
