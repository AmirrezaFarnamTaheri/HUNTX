# PR #77 final validation evidence

This note records the remediation, pre-merge review closure, and validation evidence for PR #77 (`feat/repository-wide-refinement-2026-08-19`).

## Remediation closed

The review-closure pass fixed the remaining correctness and CI issues without restoring permissive fallbacks or weakening test gates:

- build authorization is tied to the exact `source_observation_id -> seen_files.id` provenance;
- single-record test helpers and fixtures preserve that exact observation identity;
- per-format build failures escape the route worker instead of being logged and silently treated as success;
- build and publish failures classify the run before normal export decisions;
- one monotonic deadline is propagated through build, publish, publisher locks, Telegram HTTP calls, and retry sleeps;
- mutation-worker executors quiesce before a timed-out run returns;
- `DeadlineExceeded` remains a timeout signal;
- publication-history writes are idempotent;
- unknown callback actions fail closed;
- Telegram-controlled error text is bounded/sanitized and raw exception text is not logged;
- legacy tests and mocks were migrated to the exact-provenance and deadline-aware contracts;
- temporary remediation payloads and closure workflows were removed after guarded verification.

## Pre-merge review closure

### Commit-history cleanup

Before cleanup the PR was 111 commits ahead of its original base and included repeated remediation-payload staging commits plus temporary audit/remediation commits. The branch was squashed to one commit on top of the original PR base while preserving the exact pre-squash tree hash (`cd0c14d6087785a4449d3975100543a39b767321`). Final squashed commit: `8f72afdcf52a4553b5e9dd393ee8828bbf96d850`.

### Scratch-file audit

Historical commit `538b2f71634c69bea2841adb8676e73ef3eec38b` created a file named `dummy`; the blob was exactly zero bytes. Commit `1026f3fc944656f5e8d75a2d55dd8e624f011be0` removed it. Because the scratch file never contained content, there was no credential or sensitive-path material requiring `git filter-repo`; the final squash removes both scratch commits from the PR branch history.

### Historical credential audit

A temporary read-only GitHub Actions workflow ran Gitleaks v8.30.1 with `--redact=100` against all Git history reachable from the PR head (full base/main ancestry plus PR commits), excluding only generated proxy-output directories from the active pathspec. The successful scan covered 698 commits and approximately 16.15 MB of credential-bearing history and reported 222 candidates:

- 192 `generic-api-key` findings in historical `New Outputs/all_sources.npvt.decoded.json` generated proxy payload data;
- 26 `generic-api-key` findings in historical `mergebot-output/all_sources.npvt.decoded.json` generated proxy payload data;
- 3 `private-key` findings in `src/huntx/formats/common/crypto.py`, the already-known third-party/vendor decryption material;
- 1 `generic-api-key` finding in `tests/test_h3_secret_scan.py`, a secret-scanner test fixture.

No HuntX-owned Telegram, AWS, GitHub, or other first-party credential was identified by the history scan, so there is no confirmed first-party credential requiring rotation from this audit. Security issue #78 remains open to track the explicit provenance/licensing/externalization disposition for the embedded third-party decrypt material and the retention/privacy policy for historical generated proxy payloads. Secret values were not printed or attached.

### Session-lock namespace stability

Telegram process fencing does not use an ephemeral GitHub Actions hostname. `_session_lock_root()` resolves to explicit `HUNTX_SESSION_LOCK_DIR` when configured, otherwise to the machine temp directory plus a stable uid/user namespace. `_process_session_lock_path()` and the durable `session_lease_path()` derive filenames only from the SHA-256 of the configured session identity. A regression test locks the durable namespace contract to `root / "session-leases" / <session-hash>.lock`.

## Verification evidence

The guarded `PR77 Review Closure` run #18 completed successfully. Its sequence included:

1. proving the six review regressions were red before remediation;
2. verifying the staged remediation payload by exact SHA-256 before execution;
3. passing the expanded targeted regression suite;
4. passing the authoritative repository gate: workflow YAML parsing, Go formatting/race tests/vet/builds, Python dependency checks, compileall, Flake8, MyPy, and the full non-performance Pytest suite;
5. committing the verified remediation only after those gates were green.

Ordinary `pull-request-validation` run #742 completed successfully with the session-lock namespace regression test. After the history rewrite, ordinary exact-head `pull-request-validation` run **#749** completed successfully on squashed commit `8f72afdcf52a4553b5e9dd393ee8828bbf96d850`, including workflow YAML validation, the Go quality gate, and the Python quality gate.

## Release boundary

This evidence does not merge the PR. Readiness/merge lifecycle remains a maintainer action.
