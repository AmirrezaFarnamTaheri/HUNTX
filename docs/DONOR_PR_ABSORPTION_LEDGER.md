# Donor Pull-Request Absorption Ledger

## Purpose

This ledger is the closure evidence for the open donor pull requests superseded
by PR #61. “Absorbed” means every useful donor requirement, implementation idea,
test, review finding, and negative lesson has a terminal disposition in the
repository-native convergence design. It does **not** mean blindly copying every
donor file or preserving a divergent implementation.

The target remains the existing Python HUNTX product and its established
configuration, state, ingestion, build, publication, and workflow contracts.
A donor mechanism is retained only when it strengthens those contracts without
creating a second source of truth.

## Frozen donor snapshots

| Donor | Frozen head | Role |
|---|---|---|
| PR #58 | `dc3d7951c404f1e951be7347b8065d2b44f37d06` | Experimental architecture, resilience, scoring, Go engine, and forensic documentation donor |
| PR #59 | `443d169a8faa196586cceb1fe91be1f32d58d1d5` | Defensive repository-audit and hardening donor |
| PR #60 | Dependabot workflow-only PR | GitHub Actions version and immutable-pin donor |

PR #61 is the authoritative convergence target. Its latest required
`pull-request-validation` check, rather than a copied historical test count, is
the merge gate.

## Disposition vocabulary

- **Adopted** — retained substantially as-is in the target architecture.
- **Adapted** — donor intent retained through a target-native implementation.
- **Negative guardrail** — donor defect or unsafe design converted into an
  explicit prohibition, invariant, test, or safer alternative.
- **Historical only** — useful analysis retained as documentation, not as
  executable authority.
- **Rejected** — no defensible target value after review; intentionally absent.

---

## PR #59 — defensive audit and remediation

PR #59 is fully absorbed. Its source-level repairs, regression tests, and review
follow-ups are represented directly or strengthened in PR #61.

| Donor value unit | Disposition | Target evidence |
|---|---|---|
| Missing required environment variables fail loudly | Adopted | `src/huntx/config/env_expand.py`; `tests/test_env_expand.py` |
| Invalid and boolean Telegram API IDs are rejected; numeric and string zero are treated as absent | Adopted and extended | `src/huntx/config/schema.py`; `tests/test_schema_validators.py` |
| Runtime path rebinding for rejects/raw stores | Adopted | `src/huntx/store/rejects.py`; `tests/test_store_hardening.py`; `tests/test_runtime_isolation.py` |
| SHA-256 validation before raw-store reads and destructive path construction | Adopted and extended | `src/huntx/store/raw_store.py`; `tests/test_store_hardening.py` |
| Atomic UTF-8 writes with permission preservation | Adopted and extended | `src/huntx/utils/atomic.py`; `tests/test_atomic.py` |
| Malformed build results cannot abort or waste the whole publish stage | Adopted | `src/huntx/core/hardened_orchestrator.py`; timeout and orchestration tests |
| Active blob references fence destructive pruning | Adopted and extended | `src/huntx/state/repo.py`; `tests/test_prune_blob_safety.py` |
| Session-lease stale-reap race and ownership-aware cleanup | Adopted and extended | `src/huntx/core/session_lease.py`; `tests/test_session_lease.py`; `tests/test_session_lease_reap.py` |
| Event-loop-safe sync/async bridge and I/O-free destructor behavior | Adopted | `src/huntx/connectors/base.py`; Telegram connector tests |
| Opaque-bundle byte and entry limits, including pre-read size checks | Adopted | `src/huntx/formats/opaque_bundle.py`; `tests/test_opaque_bundle_bounds.py` |
| Actual-byte download caps | Adopted and strengthened | Bot API bounded reads plus MTProto `iter_download` streaming; `tests/test_download_cap.py`; `tests/test_telegram_user_streaming.py` |
| Decoder crash, collision-complexity, and malformed-input fixes | Adopted | format modules; `tests/test_format_decoder_hardening.py`; `tests/test_zip_malware.py` |
| Record fan-out deduplication | Adopted | repository build queries; `tests/test_build_record_fanout.py` |
| Transform records and file-status changes commit atomically | Adopted | `src/huntx/pipeline/transform.py`; `tests/test_transform_atomicity.py` |
| Publisher retry bound and safe multipart filename handling | Adopted | `src/huntx/publishers/telegram/publisher.py`; `tests/test_publisher_hardening.py` |
| Historical audit report | Historical only | `docs/AUDIT_2026-07-26.md`, explicitly marked as a donor snapshot and superseded by the convergence records |

### PR #59 review finding closure

The sole donor thread still displayed as unresolved concerned Telethon buffering
an entire media object before checking the 25 MiB limit. The convergence branch
implements `download_media_bounded()` with `client.iter_download()`, checks the
cap while chunks arrive, closes the stream, and uses the helper in both the
ordinary document pass and the windowed ingestion path. The behavior is covered
by `tests/test_telegram_user_streaming.py`. The finding is therefore absorbed
in the target even though the old donor thread itself remained open.

---

## PR #60 — GitHub Actions dependency updates

PR #60 is fully absorbed in the two authoritative workflows, with immutable
commit pins rather than mutable version tags.

| Action | Absorbed target pin |
|---|---|
| `actions/checkout` v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/setup-python` v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| `actions/upload-artifact` v7.0.1 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` |
| `aws-actions/configure-aws-credentials` v6.2.3 | `e6de054238d6b7531b4efff3b6587d9aade6a06c` |

The convergence branch additionally aligns PR and production validation on
`pytest-asyncio`, preserves read-only PR permissions, separates protected OIDC
jobs from unprivileged validation/runtime work, and validates documentation-only
changes through the same PR gate.

---

## PR #58 — experimental system-consolidation donor

PR #58 is completely dispositioned but intentionally not transplanted wholesale.
Its own review history demonstrated that several advertised subsystems were
partially wired, duplicated the authoritative Python runtime, or changed product
semantics without a validated contract. Safe intent was absorbed into existing
HUNTX responsibilities; unsafe mechanisms became negative guardrails.

### Runtime and orchestration

| Donor value unit | Disposition | Target-native result |
|---|---|---|
| One understandable orchestration contract | Adapted | Existing Python orchestrator hierarchy remains authoritative; the hardened path performs ingestion, transform, build, publish, export, and cleanup with explicit `completed`, `partial`, `timed_out`, and `failed` outcomes. |
| Deadline enforcement and cancellation accounting | Adopted and strengthened | Per-stage remaining-budget checks, cancellation/pending counts, source deadlines, canonical-resolution bounds, cleanup bounds, completion buffer, durable residue, and explicit timeout stage reporting. |
| Partial-output policy | Adopted | Partial export requires explicit opt-in and is regression-tested in `tests/test_orchestrator_timeout_contract.py`. |
| Windowed ingestion and bounded work | Adapted | Durable newest-first ingestion queue, bounded window pages, continuation cursors, unique lease ownership, recovery of expired leases, and release of unfinished work to residue. |
| Safe event-loop handling | Adopted | `run_sync` bridges already-running and absent event loops without deprecated global-loop assumptions. |
| Unified class replacing all orchestrators | Rejected with negative guardrail | No new parallel “unified” runtime is introduced. PR #58’s class initially skipped phases, called nonexistent methods, omitted dedup boundaries, and constructed unused components. Target behavior is integrated behind existing public contracts instead. |

### Resilience and recovery

| Donor value unit | Disposition | Target-native result |
|---|---|---|
| Prevent one failure from cascading across the run | Adapted | Source isolation, bounded reconnect/FloodWait behavior, stage-local failure accounting, durable work leases, and route/destination-level failure isolation. |
| Circuit state and recovery observability | Adapted | Monotonic source lifecycle states and timestamps, consecutive-failure tracking, legal transition enforcement, durable ingestion state, and explicit publication delivery states. |
| Generic async circuit breaker | Rejected as a separate authority | Its reviewed constructor, timing, HALF_OPEN, single-probe, and test contracts were incomplete. Responsibility-specific bounded controls are used instead of adding a second generic state machine. |
| Autonomous self-healing daemon | Rejected with negative guardrail | The donor daemon and CLI had ephemeral/no-op and connection-lifecycle problems. Target recovery is explicit, durable, auditable, and tied to queues, leases, lifecycle transitions, checkpoint validation, and operator reconciliation. |
| Runtime-global isolation | Adapted | Immutable path snapshots and instance-scoped format registries prevent later configuration or another runtime instance from redirecting live work; covered by `tests/test_runtime_isolation.py`. |

### Quality, routing, and publication

| Donor value unit | Disposition | Target-native result |
|---|---|---|
| Exclude unsafe or ineligible proxy material | Adapted | Protocol-specific URI validation, source trust/publication eligibility, persisted verdicts, governed build queries, archive/content limits, and deterministic deduplication. |
| Adaptive network latency scoring as a publication gate | Rejected as unproven product behavior | Donor reviews identified missing metrics, invalid-value behavior, disabled-benchmark data loss, incomplete edge tests, and unbounded total benchmark duration. The convergence does not silently change publication eligibility based on live network probes. |
| TCP benchmarker | Rejected from the runtime path; lessons retained | Timeout, concurrency, cancellation, and aggregate-budget requirements are retained as negative criteria for any future benchmark feature. No hidden outbound benchmarking latency is added to production. |
| Geo-routing engine | Rejected as a duplicate/experimental mechanism | Existing route/source configuration and governed build policy remain authoritative. No second route classifier or Go/Python semantic split is introduced. |
| Freshness and delivery notification intent | Adapted | Durable per-user/per-content delivery checkpoints, source lifecycle timestamps, archive-name matching, bounded FloodWait handling, explicit authorization, and resumable delivery. |
| Publication idempotency and ambiguous transport outcomes | Adopted and strengthened | Per-generation publication intents and independent destination records; confirmed destinations are not resent; `unknown_outcome` blocks automatic duplicate delivery pending reconciliation. Covered by `tests/test_publication_ledger.py` and delivery tests. |

### Parsing, performance, and language/runtime boundaries

| Donor value unit | Disposition | Target-native result |
|---|---|---|
| Stream untrusted media without unbounded memory growth | Adapted | MTProto chunk streaming with an in-transfer byte ceiling; Bot API bounded reads; bounded opaque bundles; ZIP aggregate-byte accounting; parser record/size controls. |
| Faster collision and parsing paths | Adopted where proven | Non-quadratic archive collision naming and decoder hardening are retained through the PR #59-derived format fixes and regression tests. |
| Standalone Go `huntx-engine` runtime and CLI | Rejected with negative guardrail | It duplicated parsing/routing/healing authority and carried reviewed defects in timeouts, accumulator bounds, input validation, no-op healing, and test contracts. HUNTX keeps one Python source of truth. Useful failure cases were absorbed into Python boundaries and tests rather than shipping an unintegrated second product. |
| Performance tests with machine-specific millisecond thresholds | Rejected as a merge gate | Correctness and bounded-resource tests remain authoritative; environment-sensitive microbenchmark thresholds do not gate the convergence release. |

### Documentation and review material

| Donor value unit | Disposition | Target-native result |
|---|---|---|
| Forensic inventory and architectural lessons | Historical only / adapted | The useful findings are represented by `docs/AUDIT_2026-07-26.md`, `docs/CONVERGENCE_2026-07-27.md`, this ledger, and focused user/developer documentation. |
| “Production Ready” and executive-approval claims | Rejected | Release status is derived from current checks and maintainer approval, never asserted by an audit document. |
| Local `file:///D:/...` links and stale component paths | Rejected | Repository documentation uses portable repository-relative references. |
| Push-to-main or production instructions before approval | Negative guardrail | Repository mutation and protected production execution remain explicit maintainer actions. |
| Historical test counts | Rejected as current evidence | Current GitHub Actions on the final target SHA is authoritative. |

### PR #58 review-thread disposition

Every PR #58 review family has a terminal target disposition:

- **Actual defects in shared files**—configuration validation, lease ownership,
  full-durability state, pruning safety, path precedence, bounded downloads,
  transform limits, canonical-key/dedup concerns, and format-registry failures—
  were incorporated where still applicable or superseded by stronger target
  implementations and focused tests.
- **Defects confined to excluded donor-only files**—the generic circuit breaker,
  scoring engine, benchmarker, geo/self-healing modules, Go engine, conductor
  plans, and master compendium—cannot regress the target because those files and
  authorities are not imported.
- **Useful negative lessons**—single-probe recovery, finite/validated metrics,
  aggregate network budgets, no no-op commands, bounded accumulators, portable
  documentation, final-SHA verification, and approval-gated deployment—are
  recorded here as guardrails for future work.

No unresolved PR #58 comment requires copying the reviewed donor mechanism into
PR #61. Reintroducing those mechanisms without a new product decision and their
missing contracts would reduce, not improve, convergence quality.

---

## Cross-donor target evidence

The following target tests make the absorbed invariants independently reviewable:

- `tests/test_orchestrator_timeout_contract.py`
- `tests/test_persistent_lifo_ingestion.py`
- `tests/test_runtime_isolation.py`
- `tests/test_source_lifecycle.py`
- `tests/test_publication_ledger.py`
- `tests/test_delivery_resume.py`
- `tests/test_telegram_user_streaming.py`
- `tests/test_download_cap.py`
- `tests/test_store_hardening.py`
- `tests/test_atomic.py`
- `tests/test_prune_blob_safety.py`
- `tests/test_session_lease_reap.py`
- `tests/test_transform_atomicity.py`
- `tests/test_format_decoder_hardening.py`
- `tests/test_workflow_resilience.py`
- `tests/test_runtime_generation.py`

## Closure criterion

PRs #58, #59, and #60 may be closed as superseded when:

1. this ledger is present on PR #61;
2. the latest required `pull-request-validation` run for PR #61 succeeds;
3. all inline review threads on PR #61 remain resolved; and
4. each donor receives a closure comment linking to PR #61 and explaining its
   value-level disposition.

Closing a donor does not merge its branch. PR #61 is the sole integration path.