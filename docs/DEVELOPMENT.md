# HUNTX Development Guide

This document describes the current implementation and contributor contracts. It intentionally distinguishes the governed production path from compatibility/standalone modules that still exist in the repository.

## 1. Runtime topology

HUNTX is primarily one Python application. Production construction is centralized rather than distributed across CLI callers.

```text
entrypoint
  |
  +-- huntx.cli.hardened_main     installed console wrapper
  +-- huntx.cli.main              direct module CLI
  +-- huntx.cli.commands.run      compatibility helper
  +-- GatherX AdminMixin          operator-triggered run
            |
            v
     huntx.cli.run_service
            |
     config load + validation
            |
 process + MTProto session locks
            |
 huntx.core.runtime_factory
            |
 OptimizedHardenedOrchestrator
            |
   governed ingest/transform/build/publish/export
```

Do not construct plain `Orchestrator` from a new operator-facing run path. Use `execute_pipeline_run()` for an end-user/operator run or `create_production_orchestrator()` when a lower-level test/integration explicitly owns locking and health evaluation.

## 2. Repository map

```text
src/huntx/
├── bot/                     GatherX private Telegram bot
├── cli/
│   ├── hardened_main.py     installed path/default compatibility wrapper
│   ├── main.py              argparse commands
│   ├── run_service.py       canonical governed run boundary
│   └── commands/            compatibility helpers
├── config/                  YAML/env expansion, Pydantic models, deep validation
├── connectors/
│   ├── telegram/            Bot API durable-inbox source connector
│   ├── telegram_user/       Telethon MTProto + windowed connector
│   └── v2ray_collector/     Python wrapper + Go scraper package
├── core/
│   ├── runtime_factory.py   production dependency construction
│   ├── runtime_resilience.py durable LIFO/source-governance runtime contract
│   ├── orchestrator.py      base orchestration implementation
│   ├── hardened_orchestrator.py
│   ├── optimized_orchestrator.py
│   ├── run_health.py        structured disposition/metrics
│   ├── output_ownership.py  exact generated-file ownership
│   ├── locks.py             cross-platform process/session file locking
│   └── router.py            format classification/proxy scheme vocabulary
├── formats/
│   ├── registry.py
│   ├── register_builtin.py
│   ├── proxy_uri_validator.py
│   ├── npvt.py              canonical validated proxy subscription handler
│   ├── npvtsub.py           same proxy contract, different format identity
│   ├── opaque_bundle.py     raw-blob ZIP builder contract
│   └── ...                  format-specific handlers/enrichment
├── pipeline/
│   ├── ingest.py            raw/observation ingestion
│   ├── windowed_ingest.py   MTProto page + lease checkpoint transaction
│   ├── transform.py / optimized_transform.py
│   ├── governed_build.py    publication-tier-aware record query
│   ├── build.py             artifact + derivative construction
│   └── publish.py           durable publication intent/delivery ledger
├── publishers/telegram/     Telegram Bot API document publisher
├── state/
│   ├── db.py                SQLite initialization/migrations
│   ├── schema.sql           canonical base DDL
│   ├── repo.py              repository operations
│   ├── ingestion_queue.py   persistent LIFO work/lease state
│   ├── verdict_store.py     governed record verdicts
│   └── *_hardening.py       compatibility-installed safety contracts
├── store/                   raw/artifact/reject/path ownership
└── utils/                   atomic I/O, env parsing, safe names, content checks

cmd/
├── huntx-tools/             release/output/generation/site utility CLI
└── huntx-engine/            standalone high-performance helper CLI

internal/                    Go packages used by huntx-tools
scripts/                     CI/runtime maintenance utilities
.github/workflows/           PR + production + generated-output control plane
```

Generated `outputs/` and `outputs_dev/` are publication surfaces, not source modules. Historical reports under `docs/history/` and forensic reports are evidence/knowledge artifacts, not executable architecture.

## 3. Setup

Python requires 3.11+; CI currently validates with Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

For an exact CI environment, install the hash-pinned runtime requirements and exact-version CI requirements:

```bash
python -m pip install --require-hashes --prefer-binary -r requirements.txt
python -m pip install --prefer-binary -r requirements-ci.txt
python -m pip install --no-deps -e .
```

Go uses the repository root `go.mod` and Go 1.23.1.

## 4. Required validation

PR CI executes:

```bash
# Workflow syntax
ruby -e 'require "yaml"; Dir[".github/workflows/*.{yml,yaml}"].each { |p| YAML.load_file(p) }'

# Go
test -z "$(gofmt -l .)"
go test -race ./...
go vet ./...
go build ./cmd/huntx-tools
go build ./cmd/huntx-engine

# Python
python -m pip check
python -m compileall -q -j 0 src tests scripts
python -m flake8 src/huntx tests scripts --count --statistics
python -m mypy src/huntx
python -m pytest -q -m "not perf" --strict-config --strict-markers
```

Do not weaken a gate to make a change pass. Add or adjust regression coverage when behavior changes.

## 5. Persistence invariants

SQLite uses WAL plus `synchronous=FULL` because source cursors, work leases, and publication receipts must survive acknowledged commits.

Important invariants:

- observation identity is `(source_id, external_id)`;
- raw bytes are content-addressed by SHA-256 and verified on read;
- normalized records retain observation provenance;
- Bot API updates are durably stored before advancing the remote offset;
- MTProto window page writes and queue checkpointing use one SQLite transaction;
- an active lease is valid only for its owner **and** lease token;
- source revocation invalidates unfinished work, including active leases;
- publication intent success requires all required configured destinations to be confirmed;
- unknown publication outcomes are not blindly resent;
- destructive pruning requires a positive integer retention window and rechecks raw-blob liveness after DB pruning.

When adding persistent state, update `schema.sql` when appropriate, add a guarded migration in `DBConnection`, define partial-failure/rollback behavior, and add migration regression tests.

## 6. Concurrency and lifecycle

### Runtime locks

`run_service.execute_pipeline_run()` acquires:

1. one lock for the selected state directory;
2. host/user-wide locks for every configured MTProto session identity, in sorted order.

The global session namespace prevents two HUNTX invocations with different `--data-dir` values from using the same Telethon session concurrently.

`acquire_lock()` must only translate actual lock-acquisition errors. Exceptions raised by the protected operation must propagate unchanged.

### Ingestion queue

Production MTProto ingestion uses `PersistentIngestionQueue`, not the legacy source-worker traversal as its governing scheduling primitive. Work states include pending/partial/leased/retry/quarantined/completed semantics with bounded leases and newest-window-first selection.

### Async helpers

If adding concurrent helpers:

- bound queues/workers/retries;
- define cancellation/shutdown ownership;
- serialize mutable shared state or make it immutable;
- do not share a SQLite connection concurrently without explicit locking;
- use monotonic clocks for elapsed/recovery intervals where wall-clock semantics are unnecessary.

## 7. Adding or changing a format

### Text/logical format

Implement `FormatHandler` and provide parse/build behavior when the format is publishable.

### Raw/archive format

If extending `OpaqueBundleHandler`, the normalized record **must** retain:

```text
unique_hash = SHA-256(raw source bytes)
data.blob_hash = same SHA-256
data.filename
data.size
```

Optional decryption/inspection belongs in additional metadata fields. Do not replace the canonical blob record with logical child records unless the handler also supplies a builder that consumes those logical records.

If a raw-blob-dependent format is new, ensure it is included in the state raw-retention contract so cleanup cannot delete bytes still needed for future builds.

### Registration checklist

1. implement handler under `src/huntx/formats/`;
2. add extension/content routing to `core/router.py` when needed;
3. register it in `formats/register_builtin.py`;
4. if it is user-requestable, update `bot/constants.py` (`SUPPORTED_FORMATS`, labels/auto-delivery only if intended);
5. if it is an archive publication format, update publication extension/empty-artifact rules where required;
6. add parse/build/round-trip/resource-bound tests;
7. update operator docs.

`validate_config()` uses registry build capability. Parse-only handlers must remain rejected from output routes.

## 8. Adding or changing a proxy protocol

The authoritative recognition vocabulary begins in `core/router.py` (`_PROXY_SCHEMES` plus the authenticated HTTP proxy pattern). `npvt` imports that vocabulary; `npvtsub` inherits the same handler contract.

For a new protocol:

1. define the recognized scheme/shape in the router;
2. implement protocol-aware validation in `formats/proxy_uri_validator.py`;
3. ensure remark stripping/canonical identity remains semantics-preserving;
4. update `pipeline/build.py` decoding only when the payload can be decoded correctly;
5. add sing-box conversion only when the current schema can represent the URI without inventing missing fields;
6. add valid/invalid/boundary tests and base64-subscription parity tests;
7. document whether the protocol is recognition-only or natively converted.

Do not accept a URI solely because it has a known prefix.

## 9. Adding a connector

1. implement the `SourceConnector` contract;
2. define durable acknowledgement semantics before remote offsets can advance;
3. bound downloads/input sizes and deadlines;
4. add source type/config schema and deep validation;
5. add construction to the appropriate governed runtime path;
6. decide how source trust and canonical identity interact;
7. add crash/retry/resume tests;
8. update production config only if the connector is intentionally activated.

Do not treat implementation presence as production activation.

## 10. GatherX changes

Command policy is declared in `bot/constants.py`:

- pending-safe private commands;
- approved private commands;
- private admin commands.

When adding a command:

1. decide its minimum authorization class first;
2. implement the handler in the bot mixin/handler module;
3. register it through the matching policy wrapper;
4. add it to the default Telegram command menu only if it is appropriate for non-admin users;
5. preserve the lower-level artifact authorization boundary for any file send;
6. add DM/group/pending/approved/admin regression tests.

Never use mutable usernames as administrator identity. Admin access uses numeric Telegram user IDs.

## 11. Logging and secrets

Known credential shapes are redacted both before formatting and from the final rendered record, including traceback/stack text. This is defense-in-depth; code should still avoid including credentials in exception messages, URLs, or diagnostic payloads.

Never log:

- full Telegram Bot API URLs containing tokens;
- Telethon session strings;
- API hashes;
- AWS keys/session tokens;
- decrypted secret material unless the feature explicitly requires a user-visible output and that output has a secure destination.

Secret-dependent format decryptors must fail closed when credentials are absent. The source blob should remain preservable when decryption is optional enrichment.

## 12. Go code

`cmd/huntx-tools` and `cmd/huntx-engine` share the root module/toolchain. Do not add a nested `go.mod` under `cmd/huntx-engine`.

Network benchmarking/probing must resolve once, reject loopback/private/link-local/multicast/unspecified/special-use addresses, then dial only the validated numeric public IP. Never re-resolve a validated hostname at dial time.

## 13. Production workflows

Architecturally significant workflows:

- `pr-validation.yml` — pull-request quality gate;
- `huntx.yml` — two-hour production validate/restore/run/package/persist/Pages flow;
- `publish-generated-outputs.yml` — trusted-run snapshot + generated branch + controlled `main` mirror;
- `huntx-real-investigation-gate.yml` — validates structured evidence that real sources were checked;
- `huntx-telegram-activity-gate.yml` — Telegram activity-related operational gate.

Pin third-party actions to immutable commit SHAs. If a workflow changes persistence or release state, define the verification point and failure behavior before mutating the pointer/deployment.

## 14. Standalone Go engine and next-generation helpers

`huntx-engine` and Python helper classes such as scoring/geo/self-healing/circuit-breaker components are real, tested code, but presence does not mean they are all on the current production data path. Keep docs explicit about reachability.

If one becomes production-critical, wire it through the governed runtime factory, add end-to-end evidence, and update architecture/user documentation in the same change.

## 15. Documentation truth

Update `README.md`, `docs/USER_GUIDE.md`, and this guide when a change alters:

- entrypoints/commands;
- config/environment variables;
- persistent state or migration behavior;
- source trust/auth rules;
- supported/buildable formats;
- deployment/persistence workflow;
- production reachability of a helper/tool.

Point-in-time forensic and audit documents should be preserved as history. Add a reconciliation note rather than silently rewriting their original claims.
