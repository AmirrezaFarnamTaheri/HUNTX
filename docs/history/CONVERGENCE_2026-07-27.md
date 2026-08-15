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

The maintainer authorized publishing the convergence branch and opening PR #61.
All actionable inline review threads on PR #61 are resolved. Issues #44–#47 are
linked for closure by the PR; superseded donor PR closure remains a maintainer
repository-state decision rather than an implementation side effect.

## Issue disposition

| Issue | Resolution | Primary proof |
|---|---|---|
| #44 — MTProto ownership and session locks | Client ownership is instance-scoped; sync and async acquisition use the same ownership key; cleanup is idempotent and cannot disconnect another connector; destructors perform no network work. Text and document cursors are independent and advance only after the ingestion transaction is durable. Download failures block acknowledgement instead of losing observations. | `test_telegram_user_ownership.py`, `test_telegram_user_cursor.py`, `test_ingest_ack.py` |
| #45 — orchestrator timeouts | One authoritative hardened run contract reports `completed`, `partial`, `timed_out`, or `failed`; records per-stage timing and cancellation/pending counts; prevents later phases after timeout; rejects partial export unless explicitly enabled; and keeps a blocking publisher outside the caller's timeout bound. CLI exit behavior follows that contract. | `test_orchestrator_timeout_contract.py` |
| #46 — production workflow and generated outputs | Validation is unprivileged. OIDC is confined to protected restore/persist jobs. State is restored from a verified immutable generation, handed to an unprivileged runtime job, checkpointed even on later enforcement failure, uploaded as an immutable generation, verified remotely, and exposed by advancing `current.json` last. Reset first verifies a backup pointer. Generated output is an artifact/Pages deployment, never a commit to `main`. PR validation cannot obtain cloud credentials. | `test_workflow_resilience.py`, `test_runtime_generation.py` |
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
| Action supply chain and expression injection | Official immutable action SHAs and read-only PR validation permissions. |
| Atomic writes, symlinks, raw-store integrity, archive limits | Descriptor-owned random temporary files, replacement plus POSIX directory sync, strict digest/path validation, corrupt-blob repair, symlink rejection, actual-byte and expansion limits. |
| Environment expansion, schema validation, governance | Deterministic environment handling, loud invalid credential rejection, explicit source trust requirements, fail-closed publication checks. |
| Transform, provenance, fan-out, publish idempotency | Batch transform rollback; exact source-observation provenance prevents trust inheritance through shared blob hashes; edited external items requeue and retire stale records; durable per-destination publication intents preserve partial success and retry only unconfirmed destinations. |
| Lease races, pruning, shared state | Serialized reap/claim operations, active-reference protection, strict hash validation, migration postconditions. |
| Parser/decoder correctness and complexity | Correct binary/text handling, bounded opaque bundles, non-quadratic collision naming, ZIP and Telegram byte caps, removal of dead/ambiguous handler paths. |
| Bot API confirmation and multi-chat fan-out | Each Bot API response is committed to a token-fingerprinted SQLite inbox before a higher offset can confirm it at Telegram. Independent source offsets replay the durable inbox after crashes and fan one token out safely across configured chats. |
| Queue fencing and lifecycle monotonicity | Every work-item claim has a unique lease token; stale same-owner workers cannot checkpoint a reclaimed item. Lifecycle timestamps never regress, stale successes cannot erase newer failures, and retired sources cannot silently reactivate. |
| Runtime global-state isolation | Every orchestrator snapshots immutable runtime paths and owns an isolated format registry, preventing later CLI/path reconfiguration or another runtime instance from redirecting stores or replacing handlers. |
| Ambiguous publication outcomes | Transport loss after a send is recorded as `unknown_outcome`, never as a confirmed failure. Automatic resend is blocked pending operator reconciliation, preventing duplicate documents when Telegram accepted a request but its receipt was lost. |
| Seen-file insert race | `record_file()` is installed as an atomic conflict-tolerant implementation and is covered by concurrent duplicate-observation regression testing. |
| Durable Bot API inbox retention | Per-consumer watermarks fence pruning by the slowest active consumer; watermark commit follows durable source-state persistence. |
| PR #58 Go implementation comments | Audited file-by-file and deliberately excluded: its parallel implementation remains non-authoritative, so reviewed races, DTO drift, parser divergence, global paths, and archive/reset defects are not introduced into the delivered Python runtime. Requirements with native value were reimplemented behind the existing execution contract. |

## Dependency correction

The locked `pyasn1==0.6.3` dependency was upgraded to `0.6.4` with official
PyPI wheel and source hashes. Historical local vulnerability and dependency
audit details remain in the donor audit; current merge evidence is the
repository's reproducible GitHub Actions quality gate.

## Authoritative verification evidence

The authoritative current evidence is GitHub Actions on the convergence branch,
not historical local pass counts copied from donor branches.

Implementation and workflow head `3c65372a636b0842567b199d450a0be937e7d939`
passed `pull-request-validation` run `30314387839` (run 345). The `quality-gate`
job completed successfully with all of these steps green:

- dependency installation and `pip check`;
- bytecode compilation;
- CI-gated Flake8 checks;
- mypy type checking;
- the strict pytest suite.

The PR validation workflow now includes `docs/**` in its trigger and sparse
checkout surface, so documentation-only changes also receive the same quality
gate. The production workflow installs the same async pytest dependency used by
the PR gate.

## Merge handoff

PR #61 is open, non-draft, and mergeable. Before merge:

1. require the latest successful `pull-request-validation` result;
2. perform one human maintainer review of the broad convergence scope;
3. preserve the documented residual backlog as follow-up work rather than
   silently broadening this PR again.

After merge, run one protected production workflow execution and verify the
restore, immutable checkpoint upload, remote manifest comparison, pointer-last
promotion, Pages deployment, and Telegram delivery ledger behaviour.