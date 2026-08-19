# PR #76 Review Resolution Ledger

Date: 2026-08-19

This document is the authoritative disposition of the review feedback on PR #76. The original CodeRabbit review was produced against an earlier force-updated state of the branch, so some findings describe code that is no longer present in the current diff. The dated 2026-08-17 plan files remain useful forensic/planning snapshots, but any pseudocode or contract in them that conflicts with this ledger or the current implementation is non-normative.

## Runtime fixes completed

- Secret-dependent decryptors now fail closed. Source-visible TUT, NetMod, and SlipNet fallback key material was removed. Credentials are resolved lazily from environment variables only when the sensitive operation is invoked.
- V2Ray collector IDs now use the complete content SHA-256 and no volatile line index. Ingestion performs an opt-in source-local raw-hash compatibility lookup so rows persisted under the historical 16/32-character index-dependent IDs are not re-ingested after upgrade or reorder.
- `nm` and `slipnet` remain registered for parsing, but the registry now exposes direct-build capability and config validation rejects them as direct output routes because their concrete `build()` implementations are stubs.
- The approval workflow is now operational, not merely represented in the schema: `/pending`, `/approve <id>`, and `/deny <id>` are implemented, registered, numeric-admin guarded, and covered through the same `_get_active_users()` delivery selector used at runtime.
- CLI reset/restore and bot startup no longer own shadow copies of `bot_users`/bot-delivery DDL. `schema.sql` plus DB migrations are the schema source of truth. Restore uses UPSERT rather than `INSERT OR REPLACE`, preserving delivery foreign-key rows.
- CLI prune now re-checks all surviving `seen_files.raw_hash` values after database pruning and subtracts still-live hashes before disk deletion, matching the admin fail-safe. A regression test invokes `_cmd_prune` itself.
- Reset backups are written outside `STATE_DIR`, because `STATE_DIR` is a reset target. The prior path created a backup and then deleted it in the same reset.
- `validate_config()` now accepts the `v2ray_collector` source type already accepted by the Pydantic schema and rejects contradictory Telegram credential blocks.
- Bot statistics now distinguish actual `muted=1` users from pending/unapproved users.

## Review finding disposition

1. **Stale lifecycle events can overwrite trust state** — already fixed in the current branch before this follow-up. `upsert_lifecycle_event()` guards state-bearing fields by event timestamp, and the stale-event regression covers approved-at-T+2 followed by quarantined-at-T+1.
2. **Hard-coded crypto fallbacks / fail-open default** — fixed. Fallback literals and SlipNet key fragments were removed; missing/malformed required credentials raise `MissingSecretError` in the decryptor contract.
3. **Approval tests must exercise `_get_active_users()`** — already fixed in the current branch; additional command-level coverage now proves approve/deny transitions change the real selector.
4. **V2Ray persisted external-ID compatibility** — fixed with stable full-content identity plus raw-hash compatibility lookup. This also fixes reordering-induced duplicate identity, which was not covered by the original comment.
5. **H-3 remediation must include SlipNet** — fixed; SlipNet now requires `HUNTX_SLIPNET_KEY_HEX` and contains no embedded key fragments.
6. **Secret scanner must not rely on `python -m rg`** — superseded. Regression tests inspect the relevant source directly with Python and assert the exposed literals are absent.
7. **H-6 tests should hit `_cmd_prune`** — fixed; the suite invokes the real CLI function and asserts only orphaned hashes reach `RawStore.prune_by_hashes()`.
8. **Schema drift test should compare/lock the real schema, not only a column name** — addressed structurally: CLI restore and bot startup no longer create shadow DDL. `open_db()` is authoritative and bot startup asserts canonical tables/columns exist.
9. **Register `/approve`, `/deny`, `/pending`** — fixed in `HandlersMixin._register_handlers()`; commands are implemented in `AdminMixin`.
10. **Forbidden-import tests should cover `nm`, `netmiko`, and `paramiko` prefixes** — documentation/test-plan correction. Any future dependency-boundary test must match complete import roots/prefixes rather than one literal spelling; no production dependency change is introduced here.
11. **Non-legacy harness must actually wire all consumers** — documentation correction. A future harness migration is not considered complete until construction sites and runtime consumers are switched and the legacy path is unreachable under the new mode.
12. **`validate_config` tests must pass `AppConfig`, not a dict** — corrected in the new regression suite, which constructs real Pydantic `AppConfig`/`SourceConfig`/`PublishRoute` instances.
13. **Extend the existing `FormatRegistry` API; do not replace it** — fixed. Existing `register`, `get`, `list_formats`, and `get_instance` remain intact; `can_build()` is additive.
14. **Do not count intentionally failing secret tests as a green gate** — corrected. H-3 tests now assert fail-closed behavior and pass when the remediation is correct; no intentional red test is part of the acceptance count.
15. **`seen_files` must participate in schema single-source-of-truth migration** — authoritative contract: all persistent tables, including `seen_files`, remain owned by `schema.sql` plus `DBConnection` migrations. Bot/CLI helpers must not recreate subsets independently.
16. **Use the real `RawStore` import path** — current production and regression code use `huntx.store.raw_store.RawStore` / relative equivalent.
17. **`bot_users.approved` migration must be idempotent** — already implemented in DB migrations; restore now goes through `open_db()` so it reuses that idempotent path instead of a second migration copy.
18. **Go coverage must be interpreted per package** — documentation correction. Future Go quality gates must evaluate the packages under test explicitly rather than treating one aggregate percentage as evidence that every package is covered.
19. **Secure-tier tests should catch the intended configuration error, not broad exceptions** — authoritative test guidance: assert the concrete exception contract produced by validation/runtime policy and enumerate secure/compatible/raw branches explicitly.
20. **Read secure-tier flags at validation time** — authoritative contract: environment-backed security policy is resolved when validation executes, not frozen at module import, so tests/operators can change process configuration deterministically before validation.
21. **Dead-code guard must not reject future legitimate verdict-writer callers** — documentation correction. Call-graph/dead-code tests must express allowed ownership boundaries, not a one-caller string count that blocks intended extensions.
22. **SQLite pool must reset transaction state before returning connections** — blueprint correction. Any future pooled connection implementation must rollback/clean an open transaction before reuse and must not return a connection with caller state attached.
23. **Schema-version table must be bootstrapped before it is read** — blueprint correction. Future schema-version logic must create/bootstrap version metadata before querying it and remain safe on an empty database.
24. **M-1 test must exercise the `nm` route** — fixed at the actual contract level: the regression constructs an `AppConfig` whose output format is `nm` and asserts validation rejects the parse-only route.
25. **Changelog gate test should execute the gate script** — documentation correction. A future release-governance test must run the real script/entrypoint and assert exit status/output, not duplicate its logic in Python.
26. **Detect concrete `NotImplementedError` build stubs** — fixed explicitly through registry build capability. `nm` and `slipnet` remain parse-capable but are not accepted as direct build outputs.
27. **Telemetry tests should be behavioral, not source-string checks** — documentation correction. Future telemetry acceptance tests must execute the instrumented path and assert emitted measurements/events.
28. **Rate-limit identity/contract must consistently use `event.sender_id`** — current runtime rate limiting and new admin authorization use immutable numeric sender IDs. Username is never accepted as an authorization identity.
29. **`npvtsub` parser contract must be consistent** — documentation correction. New work must preserve the currently exported parser/handler contract rather than inventing a different return type in plan pseudocode.
30. **Wave 5 documentation deliverables must be internally consistent** — the 2026-08-17 wave files are explicitly historical snapshots; this ledger is the reconciliation point for conflicting future-work statements.
31. **Secure-tier validation/persistence/orchestrator contract must agree** — authoritative rule: one effective publication tier must flow from validated config into runtime policy; persistence and orchestration must not independently reinterpret an environment flag.
32. **Go `sitegen` examples must match the actual API/context contract** — documentation correction. Future implementation/testing must compile against current exported signatures and pass context/cancellation through the real API.
33. **GitHub Actions examples must pin third-party actions immutably** — authoritative CI guidance: new/edited workflow examples should use immutable commit SHAs for third-party actions where repository policy requires pinning.
34. **Do not globally exclude gosec G401** — authoritative security guidance: weak-crypto findings must be handled locally with a justified exception only where protocol compatibility requires it, not disabled repository-wide.
35. **Go test snippets must use actual module/exported APIs** — documentation correction. Acceptance is compilation/execution against the repository module, not illustrative pseudocode that names nonexistent symbols.
36. **Forensic artifact-download gates must fail closed and validate diagnostics** — authoritative CI guidance: required evidence/download failures fail the gate, and artifact validation must verify expected diagnostic content/shape rather than mere file existence.
37. **Git-history claims must be scoped to observed history** — corrected interpretation: forensic statements describe the refs/history inspected for the audit and are not claims that unreachable/deleted objects never existed.
38. **Flake8 cleanup in new tests** — stale against the current branch and revalidated by fresh CI; new regression files also avoid unused imports.
39. **Use portable environment access, not `os.environb`** — current security helpers use `os.environ.get()` and encode explicitly.

## Additional defects found during the follow-up review

These were not required to close the original comments but were found while tracing the same code paths:

- `validate_config()` accepted only Telegram source types even though the schema accepted `v2ray_collector`; fixed.
- V2Ray external IDs depended on scraper output index, so line reordering manufactured new observations; fixed with index-independent content identity.
- `_cmd_prune` could delete a content-addressed blob still referenced by a newer `seen_files` row sharing the same hash; fixed with a post-prune live-hash subtraction.
- `_cmd_reset` stored its safety backup in a directory that the reset immediately deleted; fixed and regression-tested.
- `_get_user_count()` conflated pending approval with muted state; fixed.
- `INSERT OR REPLACE` during subscriber restoration could delete/reinsert a parent row and cascade delivery history; replaced with `ON CONFLICT ... DO UPDATE`.

## Verification contract

The PR is not considered complete solely because an older workflow run was green. The acceptance state is the GitHub Actions `pull-request-validation` run for the final head commit after these changes. The PR body should report that final run rather than retaining the earlier `577 passed` claim if the final count/status differs.
