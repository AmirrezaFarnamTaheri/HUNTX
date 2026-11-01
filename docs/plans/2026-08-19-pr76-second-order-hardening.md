# PR #76 Second-Order Hardening Audit

Date: 2026-08-19

This report records the second-order review performed after the original PR #76 finding-resolution pass. The goal was not to repeat the original 39 CodeRabbit findings, but to search for *policy gaps between layers*: code that was individually correct yet could still be bypassed by another entry point, stale historical state, a monkey-patched runtime, a nested module outside CI, or a validation/observability contract that existed only on paper.

The original finding ledger remains authoritative for the first review pass:

- `docs/plans/2026-08-19-pr76-review-resolution.md`

This document is the companion record for the broader follow-up.

## Executive conclusion

The follow-up found multiple production-reachable defects that would not have been caught by a file-by-file review alone. The most important classes were:

1. authorization applied only at the caller instead of at the delivery boundary;
2. source trust applied only to new ingestion but not persistent queues/historical build records/dev outputs;
3. different runtime graphs for CLI, bot-admin and the public `UnifiedOrchestrator`;
4. deadline/cancellation gaps around transformation and the Go collector subprocess;
5. SSRF-capable reachability helpers in Python, the Go collector, and the nested Go engine;
6. a persistent LIFO retry starvation edge case;
7. an investigation workflow that did not actually inspect its claimed evidence;
8. a nested Go module and checked-in executables that were outside the root Go quality gate;
9. identity truncation, unbounded recursive base64 parsing and unsafe URI classification in that nested module.

All high-severity and directly production-reachable defects found in this pass were remediated and regression-tested. Remaining items are listed explicitly under **Residual risks / follow-up** rather than being represented as fixed.

---

## A. GatherX authorization and delivery identity

### A1. Pending users could fetch protected artifacts — fixed

The approval bit originally controlled automatic delivery, but `/get`, `/latest`, and inline `get:*` callbacks could still retrieve artifacts before approval.

Remediation:

- protected handlers now require approval;
- artifact callbacks require approval;
- lower-level delivery helpers independently re-check authorization so a future handler cannot accidentally bypass policy.

### A2. Approved users could redirect delivery into a group/channel — fixed

GatherX is a private-user delivery bot, but registration previously stored arbitrary `event.chat_id`. Invoking a command from a group could therefore update an approved user's saved delivery chat to that group.

Remediation:

- registration accepts only `chat_id == user_id`;
- automatic delivery selects only rows where `approved = 1`, `muted = 0`, and `chat_id = user_id`;
- protected callbacks require a private event;
- lower-level delivery refuses non-private/non-approved identities;
- legacy database rows whose `chat_id` is a group/channel are no longer active delivery targets.

### A3. Known Telegram usernames could be erased — fixed

Repeated command registration with `username=None` previously overwrote a known username with NULL.

Remediation: metadata refresh uses `COALESCE(new_username, username)`.

### A4. Malformed FloodWait environment settings could crash delivery — fixed

Raw `int(os.environ[...])` conversions made malformed configuration a runtime exception path.

Remediation: bounded integer parsing with safe defaults and maximum retry/wait bounds.

---

## B. Runtime graph and governance consistency

### B1. Public `UnifiedOrchestrator` was not actually the production graph — fixed

It maintained a separate execution flow that skipped normal ingestion semantics and could swallow transform failures.

Remediation: `UnifiedOrchestrator` is now a thin facade over the optimized hardened production orchestrator; it adds helper components/metadata but delegates the run contract.

### B2. CLI and bot-admin constructed different pipelines — fixed

`huntx` CLI used the hardened stack while `/admin run` constructed a weaker plain orchestrator.

Remediation: `src/huntx/core/runtime_factory.py` is the single production constructor. CLI and bot-admin both use it, including:

- runtime resilience installation;
- optimized persistent-window ingestion;
- source governance;
- governed build/publication tiers;
- consumer reconciliation;
- process/session locking;
- the same run-health decision.

### B3. Runtime hardening depended on one import side effect — fixed

`runtime_resilience` was formerly applied by the CLI import path. A caller using the runtime factory directly could have missed it.

Remediation: the production runtime factory calls `apply_runtime_resilience()` itself.

### B4. Obsolete legacy async orchestration remained callable — fixed

A stale `_run_async_legacy` graph could bypass newer safety contracts if called directly.

Remediation: when runtime resilience is installed, the obsolete path fails closed with an explicit error.

---

## C. Source trust across persistent and historical state

### C1. Candidate/quarantined MTProto sources could enter the persistent queue — fixed

The optimized queue was seeded before the base hardened orchestrator filtered publication-ineligible sources.

A deeper check found an additional complication: `runtime_resilience.py` monkey-patched the optimized runner, overriding the nominal class implementation and reintroducing the unsafe source list on the real CLI path.

Remediation in the *effective runtime*:

- partition approved/rejected sources before canonicalization and queue seeding;
- terminalize pending/partial/retry work for rejected sources;
- canonicalize only approved sources;
- seed the persistent queue with only the approved canonical set;
- pass the same set to the downstream hardened runner;
- restore original configuration after the run;
- expose approved/excluded/canonical counts in the summary.

### C2. Historical records from a newly unapproved source could still build — fixed

Filtering only new ingestion was insufficient because route builds could include old records from sources whose trust state changed later.

Remediation: each route's build source list is intersected with the current publication-eligible source set.

### C3. Cumulative dev output could retain revoked source material — fixed

The dev manifest was append-only. A URI could therefore remain in cumulative output after its only source became quarantined/retired.

Remediation:

- canonical manifest entries are intersected with active records backed by currently approved sources;
- revoked entries are removed before and after cumulative export;
- stale rendered dev proxy files are removed when no approved manifest entries remain.

---

## D. Deadline, subprocess and concurrency semantics

### D1. Transformation could overrun the global run deadline — fixed

The hardened runner bounded ingestion/build/publish but called transformation without a deadline.

Remediation:

- pass the monotonic deadline into transformation;
- consume the transform completion/stop-reason contract;
- mark transformation deadline exhaustion as a real timeout;
- do not continue into build after an incomplete transform.

### D2. Go collector subprocess ignored the orchestrator deadline — fixed

The executor task could be cancelled while `go run` continued in the worker thread and later wrote output into a subsequent run.

Remediation:

- collector subprocess timeout is bounded by the remaining global deadline and a hard cap;
- no subprocess launch after deadline exhaustion;
- `TimeoutExpired` is handled explicitly;
- stale output is deleted before launch and never consumed after a failed run.

### D3. Go collector logged raw subprocess output — fixed

Proxy share URIs often contain UUIDs, passwords/userinfo and other credential-like material. Raw stdout/stderr logging could leak that material into CI logs.

Remediation: only bounded diagnostic byte counts/status are logged, not raw subprocess content.

### D4. Persistent LIFO retry starvation — fixed

A newest-window `retry_wait` row with a *future* retry timestamp was allowed to define the newest incomplete window, but was not claimable. That blocked all older ready work until the retry delay expired.

Remediation:

- future deferred retries yield to older ready windows;
- due retries regain newest-window priority;
- actively leased newest-window work still preserves LIFO ordering.

---

## E. Network safety / SSRF

### E1. Python latency benchmarker could probe internal networks — fixed

Proxy hosts were resolved and dialed without excluding loopback/private/link-local/reserved addresses.

Remediation:

- resolve once;
- accept only globally routable addresses;
- reject private, loopback, link-local, multicast, unspecified and reserved ranges;
- dial the accepted numeric address to avoid DNS rebinding between validation and connection.

### E2. Go collector's “working Iranian config” probe could probe internal networks — fixed

The Go collector independently resolved and dialed scraped endpoints.

Remediation:

- explicit IPv4/IPv6 special-use blocklist plus Go address-property checks;
- literal private endpoints rejected before dial;
- DNS answers filtered to safe public addresses;
- connection uses validated numeric address and `net.JoinHostPort`.

### E3. Nested `huntx-engine benchmark` repeated the SSRF problem — fixed

The nested Go engine accepted arbitrary `host:port` targets and used `net.Dialer` directly.

Remediation mirrors the public-endpoint policy above, with direct nested-module tests for loopback, RFC1918, CGNAT, link-local, documentation/reserved IPv4 and IPv6 ranges.

---

## F. Go collector integration correctness

### F1. Long-form Hysteria2 support passed tests but was absent in production — fixed

The long-form matcher lived in `protocol_extensions.go`, but the Python wrapper executed:

`go run main.go`

which compiles only that named file and excludes sibling Go files.

Remediation: invoke the package with `go run .`, so the tested package is the executed package.

### F2. VMess endpoint parsing assumed one base64/port representation — fixed

Remediation adds standard/raw/URL-safe base64 variants, string/number port handling, and explicit port-range validation.

---

## G. Configuration and output identity

### G1. Distinct route names could collide after filesystem sanitization — fixed

Artifact paths use a sanitized route component. Distinct configured route names could collapse onto one output name.

Remediation rejects:

- duplicate route names;
- non-canonical filesystem route names;
- duplicate route source references;
- duplicate route formats;
- duplicate destination identities.

### G2. Ambiguous route prefixes could cross stale-output ownership — mitigated

The existing stale-output cleanup owns files by route prefix. Names such as `prod` and `production` are therefore ambiguous.

Current remediation rejects route names that prefix one another. A future cleanup refactor should encode ownership structurally and then this configuration restriction can be relaxed.

### G3. Optional publication destinations were a dead contract — fixed

Publisher logic supported `required=False`, but the Pydantic schema/orchestrator dropped it.

Remediation:

- `DestinationConfig.required` is now part of validated configuration;
- the orchestrator carries it to the publish pipeline;
- behavior is regression-tested.

---

## H. CI, observability and supply chain

### H1. “Real Investigation Gate” did not investigate anything — fixed

The workflow previously:

- used an unpinned `actions/github-script@v9` reference;
- checked only that an artifact with a matching name existed;
- did not download or parse the evidence;
- merely echoed the names of metrics it claimed to require.

Remediation:

- pin `actions/github-script` to an immutable commit;
- resolve a concrete completed production run;
- download the non-expired `huntx-logs-*` artifact;
- require and parse `run-summary.json`;
- enforce schema version and nonnegative integer metrics:
  - `sources_checked`;
  - `messages_scanned`;
  - `messages_new`;
  - `cursor_updates`;
- fail if approved sources existed but no source was actually checked;
- preserve the validated evidence as a follow-up artifact.

### H2. Runtime did not emit the claimed investigation metrics — fixed

The workflow could not be made real until the runtime emitted real evidence.

The optimized runner now tracks:

- unique sources actually attempted;
- messages scanned;
- newly ingested items;
- successful cursor/page checkpoints.

Those fields are added to the structured run summary in both the nominal and resilience-patched optimized runtime.

### H3. Checked-in executable binaries had no provenance need — fixed

Two identical ~4.5 MB Windows executables were tracked under `cmd/huntx-engine/`, with no runtime reference.

Remediation:

- remove both generated `.exe` files;
- ignore future generated engine executables.

### H4. Nested `cmd/huntx-engine` module was outside root Go CI — fixed

It has its own `go.mod`, so root `go test ./...` / `go vet ./...` do not traverse it.

Remediation: PR validation now uses a second pinned `setup-go` invocation with the nested module's declared toolchain and runs:

- `gofmt`;
- `go test -race ./...`;
- `go vet ./...`;
- `go build .`.

---

## I. Nested `huntx-engine` correctness discovered after bringing it into CI

### I1. Stream identity was truncated to 64 bits — fixed

`HashURI` used only the first eight bytes of SHA-256, recreating the collision class already removed elsewhere in HUNTX.

Remediation: full 256-bit SHA-256 hex identity.

### I2. Recursive base64 parsing was unbounded — fixed

Arbitrary base64-looking input could recursively decode without a nesting/decompressed-byte budget.

Remediation:

- bounded decoded byte budget;
- bounded nesting depth;
- standard/raw/URL-safe base64 support;
- incidental prose/base64-looking garbage does not poison already-valid records.

### I3. Any `://` line was accepted as a proxy — fixed

Ordinary web URLs and arbitrary schemes could become proxy records.

Remediation: explicit proxy-scheme allowlist and ordinary-web/prose rejection.

### I4. Stream parser did not deduplicate records — fixed

Remediation: deduplicate by full canonical URI identity during parsing.

### I5. Georouting searched the full URI for country substrings — fixed

Strings such as `.de` inside a password, path or query parameter could spoof the node's country.

Remediation:

- parse structured URI fields;
- infer from a decoded remark country token or the final hostname TLD only;
- remove the unnecessary unbounded per-URI georouting cache.

### I6. Healing daemon exposed mutable internal nodes after unlocking — fixed

`GetDueForRetest` returned pointers to internal state after releasing the mutex.

Remediation:

- return defensive copies;
- stable due-node ordering;
- ignore nonpositive custom backoff durations and retain a positive fallback;
- nonpositive stale-purge age is a no-op rather than an “erase everything” operation.

---

## J. Validation performed after the second-order changes

Two independent validation paths are used:

1. **Repository CI:** the latest exact branch head must have a completed successful `pull-request-validation` run. This now includes both the root Go module and the nested `cmd/huntx-engine` module.
2. **Assembled-tree validation:** a fresh branch archive was extracted separately and exercised with:
   - Python `compileall`;
   - full non-performance Pytest suite;
   - Flake8;
   - MyPy;
   - root Go `gofmt`, race tests, vet and build;
   - nested-engine `gofmt`, race tests, vet and build;
   - static search for high-risk primitives such as disabled TLS verification, `shell=True`, unsafe YAML/pickle/eval/exec, `mktemp`, `os.system`, and blanket archive extraction.

The exact-head GitHub PR gate and the independent assembled-tree checks are required to be green before this report is considered complete.

---

## Residual risks / follow-up

These are deliberately *not* presented as resolved:

1. **Production workflow QA-tool versions are not fully reproducible.** The large scheduled production workflow installs Flake8/MyPy/Pytest/type stubs without exact versions, while PR validation pins exact versions. A future cleanup should move CI tool versions into one locked/central constraints source and consume it from both workflows.
2. **Pending users can still access some non-artifact informational bot commands.** Artifact access and delivery are approval-gated/private-chat-only, but aggregate informational commands such as protocol/format help—and depending on handler policy, operational counts/status—should be explicitly classified as public vs approved-only rather than relying on historical behavior.
3. **Route-prefix safety is currently enforced by configuration rejection.** The stronger long-term design is structural artifact ownership (route ID/manifest) rather than filename-prefix ownership; after that migration the prefix-name restriction can be relaxed.
4. **Active leased work for a source is not forcibly stolen when source trust is revoked.** Pending/partial/retry work is terminalized. Existing live leases are allowed to expire/release normally to avoid corrupting concurrent ownership. The process lock prevents this in normal production, but direct library users should preserve the single-runner contract.
5. **The nested engine is now tested but remains a separate module/toolchain.** Keeping it is reasonable only if it has a clear deployment/use case; otherwise folding it into the root Go module would reduce maintenance and dependency/toolchain drift.

These residual items are materially lower risk than the production-reachable defects fixed above, but they should remain visible in future planning and review.