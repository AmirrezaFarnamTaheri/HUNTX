# HUNTX Open-Issue and Pull-Request Convergence — 2026-07-27

## Scope and decision

This branch is a clean convergence from `origin/main@4da38faf33eeed5226055ac138e3148b5d8fa569`.
It resolves the four open issues and consolidates the useful, reviewable parts
of all three open pull requests without inheriting PR #58's unsafe experimental
architecture wholesale.

The review covered issue bodies and comments for #44–#47, PR bodies, commits,
checks, reviews, review threads, and general comments for #58–#60. Repeated
comments were normalized into the disposition families below so that one
invariant has one implementation and one proof instead of several competing
patches.

The maintainer subsequently authorized publishing this branch and opening one
replacement pull request. Issues, review threads, and superseded pull requests
remain otherwise unchanged; nothing is merged or closed by this worktree.

## Issue disposition

| Issue | Resolution | Primary proof |
|---|---|---|
| #44 — MTProto ownership and session locks | Client ownership is instance-scoped; sync and async acquisition use the same ownership key; cleanup is idempotent and cannot disconnect another connector; destructors perform no network work. Text and document cursors are independent and advance only after the ingestion transaction is durable. Download failures block acknowledgement instead of losing observations. | `test_telegram_user_ownership.py`, `test_telegram_user_cursor.py`, `test_ingest_ack.py` |
| #45 — orchestrator timeouts | One authoritative hardened run contract reports `completed`, `partial`, `timed_out`, or `failed`; records per-stage timing and cancellation/pending counts; prevents later phases after timeout; rejects partial export unless explicitly enabled; and keeps a blocking publisher outside the caller's timeout bound. CLI exit behavior follows that contract. | `test_orchestrator_timeout_contract.py` |
| #46 — production workflow and generated outputs | Validation is unprivileged. OIDC is confined to protected restore/persist jobs. State is restored from a verified immutable generation, handed to an unprivileged runtime job, checkpointed even on later enforcement failure, uploaded as an immutable generation, verified remotely, and exposed by advancing `current.json` last. Reset first verifies a backup pointer. Generated output is an artifact/Pages deployment, never a commit to `main`. PR validation cannot obtain cloud credentials. | `test_workflow_resilience.py`, `test_runtime_generation.py`, Actionlint |
| #47 — interactive bot | Callback work is cost-throttled with bounded state and admin exemption; shared tokens fail closed unless explicitly allowed; registration is separated from authorization and automatic delivery requires explicit approval; delivery retries bounded FloodWaits; matching includes generated archive names; errors do not disclose tokens. Per-user, per-content delivery checkpoints persist every successful file, so retries resume without duplicates while changed content is delivered again. | `test_bot_interactive.py`, `test_bot_runtime_hardening.py`, `test_bot_authorization.py`, `test_delivery_resume.py`, `test_publisher_hardening.py` |

## Pull-request disposition

| PR | Disposition |
|---|---|
| #58 | Superseded as an integration branch. Its useful requirements were reimplemented selectively, while the reviewed unsafe expansion (divergent Go/Python runtime, shared global paths, fail-open governance, mutable telemetry, unsafe reset/archive paths, and incomplete cloud-generation protocol) was not introduced. The resulting branch has one Python execution contract and verified state-generation boundaries. |
| #59 | Used as the defensive-hardening donor, then corrected and extended for the four issue contracts. Its store, decoder, configuration, lease, publishing, size-bound, and atomicity repairs are retained. Its historical audit is preserved but marked superseded. |
| #60 | Integrated after independently verifying each official action release commit. The production workflow pins Checkout `v7.0.1`, Setup Python `v7.0.0`, Upload Artifact `v7.0.1`, Download Artifact `v8.0.0`, and Configure AWS Credentials `v6.2.3` by immutable SHA. |

## Review-comment disposition register

| Comment family | Unified resolution |
|---|---|
| Runtime timeout, cancellation, accounting, healing | Explicit terminal states, stage timings, pending/cancelled counts, bounded executor shutdown, no post-timeout phases, partial-output opt-in. |
| MTProto ownership, cache sharing, observation identity, cursor-before-ack | Instance ownership keys, exact lock cleanup, independent source cursors, pending acknowledgements, transaction-after-yield acknowledgement. |
| Bot callback abuse, token isolation, FloodWait, archive matching, duplicate delivery | Cost-based bounded throttle, fail-closed token policy, capped retry, complete generated-name matching, durable content-addressed per-user checkpoints. |
| OIDC trust, cloud persistence, reset, generated commits, checkpoints | Separate unprivileged validation/runtime jobs from protected OIDC jobs; immutable generations; strict manifests; verified backup-before-reset; pointer-last publication; no generated commits. |
| Action supply chain and expression injection | Official immutable action SHAs; PR branch name passes through an environment boundary before shell use; Actionlint is clean. |
| Atomic writes, symlinks, raw-store integrity, archive limits | Descriptor-owned random temporary files, replacement plus POSIX directory sync, strict digest/path validation, corrupt-blob repair, symlink rejection, actual-byte and expansion limits. |
| Environment expansion, schema validation, governance | Deterministic environment handling, loud invalid credential rejection, explicit source trust requirements, fail-closed publication checks. |
| Transform, provenance, fan-out, publish idempotency | Batch transform rollback; exact source-observation provenance prevents trust inheritance through shared blob hashes; edited external items requeue and retire stale records; durable per-destination publication intents preserve partial success and retry only unconfirmed destinations. |
| Lease races, pruning, shared state | Serialized reap/claim operations, active-reference protection, strict hash validation, migration postconditions. |
| Parser/decoder correctness and complexity | Correct binary/text handling, bounded opaque bundles, non-quadratic collision naming, ZIP and Telegram byte caps, removal of dead/ambiguous handler paths. |
| Bot API confirmation and multi-chat fan-out | Each Bot API response is committed to a token-fingerprinted SQLite inbox before a higher offset can confirm it at Telegram. Independent source offsets replay the durable inbox after crashes and fan one token out safely across configured chats. |
| Queue fencing and lifecycle monotonicity | Every work-item claim has a unique lease token; stale same-owner workers cannot checkpoint a reclaimed item. Lifecycle timestamps never regress, stale successes cannot erase newer failures, and retired sources cannot silently reactivate. |
| Runtime global-state isolation | Every orchestrator snapshots immutable runtime paths and owns an isolated format registry, preventing later CLI/path reconfiguration or another runtime instance from redirecting stores or replacing handlers. |
| Ambiguous publication outcomes | Transport loss after a send is recorded as `unknown_outcome`, never as a confirmed failure. Automatic resend is blocked pending operator reconciliation, preventing duplicate documents when Telegram accepted a request but its receipt was lost. |
| PR #58 Go implementation comments | Audited file-by-file and deliberately excluded: its parallel implementation remains non-authoritative, so reviewed races, DTO drift, parser divergence, global paths, and archive/reset defects are not introduced into the delivered Python runtime. Requirements with native value were reimplemented behind the existing execution contract. |
| Documentation and CI claims | Historical claims are marked as such; this document records the converged branch and the complete current verification matrix. |

## Additional defect found during convergence

The locked `pyasn1==0.6.3` dependency had five OSV advisories. It is upgraded
to `0.6.4` with official PyPI wheel and source hashes. A clean virtual
environment accepts the hash-locked install and reports no broken
requirements; the final OSV audit reports no known vulnerabilities.

## Verification matrix

| Gate | Result |
|---|---|
| Tests | `409 passed, 1 skipped` (the skip is a Windows symlink-permission case) |
| Static typing | `mypy`: no issues in 76 source files |
| Formatting | Black check: 155 files unchanged |
| Lint | Full `src/huntx`, `tests`, and `scripts` Flake8: 0 findings |
| Workflow syntax | All workflow YAML parses successfully |
| Workflow semantics/security | Actionlint: 0 findings |
| Dependency integrity | Clean hash-locked virtual-environment install; `pip check`: no broken requirements |
| Vulnerabilities | `pip-audit` with OSV: no known vulnerabilities |
| Bytecode | `compileall`: success |
| Patch hygiene | `git diff --check`: success |

The full-suite pytest process exits successfully when its temporary directory
is placed on the workspace volume. The host's system C: volume has no free
space, so validation that uses temporary files was intentionally redirected to
D:; this is an environmental constraint, not a repository failure.

Coverage measurement is 67% across the inherited repository. The remediated
contracts have focused regression tests, but the repository does not yet meet
the aspirational 80% project-wide threshold. This is recorded explicitly
rather than masking legacy modules with coverage exclusions.

## Maintainer handoff

After approval to mutate GitHub state:

1. Push `codex/open-issue-convergence` and open one replacement convergence PR.
2. Link this register in #44–#47 and request closure by the replacement PR.
3. Close #58 and #59 as superseded, and #60 as incorporated.
4. Require the same validation, type, lint, Actionlint, and dependency gates
   before merge.
