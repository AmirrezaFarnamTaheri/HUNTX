# HuntX Master Audit Report

**Date:** 2026-04-29  
**Subject:** `AmirrezaFarnamTaheri/HUNTX`, including pipeline, Telegram ingestion, GatherX bot, static site, generated artifacts, CI/CD, configuration, tests, security posture, and roadmap.  
**Status:** Final consolidated audit report. The three provided HuntX audits have been merged, deduplicated, reconciled, and polished into one coherent document.

---

## 0. Method and Evidence Rules

This report consolidates three HuntX audit drafts. The inputs had different evidence levels. One report was access-limited and could not clone the repository, but inspected public repository views, rendered files, and sampled artifacts. Another pass used repository connector/source views for deeper static inspection. A third report claims commit-specific file-by-file coverage at commit `0c77ba4cdfee27f6602385f096703a8f1a9e5239` dated 2026-04-28.

Evidence labels used here:

- **Confirmed from inspected files:** directly asserted by the stronger static/file-level audits.
- **Confirmed public/inventory evidence:** supported by repository inventory, docs, public artifacts, or visible static-site state.
- **Needs runtime verification:** source-level behavior is plausible or directly asserted, but local tests, Telegram/S3 integration, browser checks, or full artifact decoding were not executed.
- **Strategic recommendation:** roadmap, architecture, product, or governance improvement rather than a current proven defect.

This report merges duplicate findings and preserves unique details. When the inputs conflict, the safer interpretation is used and the item is marked for verification.

---

## 1. Executive Summary

HuntX is a real and non-trivial Python project. Its intended product is a zero-budget Telegram-sourced proxy/config aggregation system: it ingests Telegram messages and documents, stores raw blobs, parses supported formats, deduplicates normalized records, builds artifacts such as decoded JSON and Base64 subscriptions, publishes changed artifacts to Telegram, supports user-facing delivery through the GatherX bot, and exposes artifacts through a static website/catalog.

The project has meaningful strengths: modular Telegram connectors, content-addressed raw storage, atomic-write helpers, SQLite WAL state, a format registry, batch inserts, route/format artifact generation, Telegram publishing, a static artifact browser, and broad test-file coverage by area. It is not empty or decorative.

The central problem is operational governance. HuntX is wired to run, publish, and commit generated proxy artifacts, but the scheduled workflow does not enforce tests, linting, type checks, frontend catalog generation, full safety validation, or artifact security gates before committing outputs. Several docs and user-facing promises are ahead of the implementation, especially around GatherX commands, workflow reset safety, frontend catalog freshness, and dry-run/publish semantics.

The most urgent fixes are:

1. Add CI quality and safety gates before scheduled publish/commit.
2. Stop committing large generated proxy artifacts directly to `main` until they are scanned and governed.
3. Replace boolean destructive reset with explicit confirmation and backup behavior.
4. Fix GatherX `/get <format>` runtime path and align bot commands with docs.
5. Add strict configuration and environment-variable validation.
6. Make missing publish tokens fail in production/CI strict mode.
7. Regenerate or remove stale frontend catalog data.
8. Add path-safety to artifact route/format names.
9. Harden Telegram ingestion against FloodWait, renamed APKs, executable payloads, and publishing API errors.
10. Add parser, output, bot, workflow, and frontend regression tests.

---

## 2. Project Understanding

The intended HuntX workflow is:

```text
Telegram sources
  -> Bot API and/or Telethon MTProto ingestion
  -> media/text filtering and APK rejection
  -> content-addressed raw storage under data/raw
  -> pending-file state in SQLite
  -> format detection and parsing
  -> normalized proxy/config records
  -> route and format grouping
  -> decoded JSON, native artifacts, Base64 subscriptions, archives
  -> Telegram publishing of changed artifacts
  -> GatherX bot delivery to subscribers
  -> outputs/outputs_dev export
  -> docs/artifacts and docs/catalog.json for static frontend
```

Primary actors are:

- The repository/operator running scheduled CI.
- Telegram source owners/channels.
- Telegram users interacting with GatherX.
- Developers adding formats, sources, routes, and deployment modes.
- Static website users browsing artifacts.

Runtime environments include local Python CLI, GitHub Actions on Ubuntu/Python 3.12, optional S3 persistence, Telegram Bot API, Telethon MTProto user sessions, optional systemd/VPS deployment, and GitHub Pages/static site delivery.

The core safety requirement is that missing credentials, invalid config, failed state writes, stale catalogs, unsafe route names, malformed inputs, and publication failures must fail clearly before the system publishes, commits, or deletes state.

---

## 3. Coverage and Audit Limitations

Observed repository areas include:

- Top-level metadata: README, `pyproject.toml`, `.flake8`, `.gitattributes`, `.gitignore`, docs, config, workflows, scripts, and package metadata.
- Config: `configs/config.prod.yaml` with many Telegram sources, credentials via environment variables, routes, destinations, and output formats.
- Backend package: `src/huntx`, including CLI, config loading, connectors, core orchestrator, stores, state, formats, publishers, bot, pipeline helpers, and utilities.
- Telegram connectors: Bot API and Telethon/MTProto paths.
- Formats: NPVT/NPVT sub, OpenVPN and opaque/binary handlers, and other format handlers that need deeper parser tests.
- State/storage: SQLite schema, repository layer, raw store, artifact store, WAL mode, migrations, and published hash tracking.
- GatherX bot: interactive commands, user preferences, delivery state, file sending, and callbacks.
- Static frontend: `docs/index.html`, `docs/catalog.json`, `docs/assets/js/*`, search/filter/catalog components, CDN dependencies, and artifact links.
- Workflows: `huntx.yml` and related CI/deployment behavior.
- Generated artifacts: `outputs/`, `outputs_dev/`, `data_archive/`, decoded JSON, Base64 subscriptions, ZIPs, and catalog artifacts.
- Tests: broad filename coverage across connectors, bot, formats, router, pipeline, state, stores, atomic writes, APK skipping, publisher, config, migrations, and concurrency.

Not fully verified:

- Full local clone/test/lint/type-check execution.
- Live Telegram behavior and real FloodWait handling.
- S3 restore/persist semantics with disposable bucket.
- Full generated artifact decoding and secret scanning.
- Git history scanning for leaked tokens/sessions/artifacts.
- Browser-rendered frontend behavior under Playwright/Cypress.
- Systemd/VPS deployment behavior.
- Every parser/format handler under malformed/fuzz input.

---

## 4. Critical Findings

### C1. Scheduled CI Publishes and Commits Without Quality Gates

**Evidence level:** Confirmed from inspected workflow descriptions.  
**Severity:** Critical.  
**Area:** CI/CD, release safety.

The scheduled workflow installs the runtime package, runs `huntx`, verifies/packages output, uploads artifacts/logs, commits `outputs/` and `outputs_dev/` back to `main`, and persists S3 state. It does not run the documented development quality checks before publication: `pytest`, `black --check`, `flake8`, `mypy`, compile checks, frontend generation, or a full artifact security/schema gate.

This means broken bot paths, stale frontend catalog data, parser regressions, unsafe artifacts, and documentation drift can be published on a scheduled run.

**Fix:** Split PR validation and scheduled publish. Required PR CI should install dev extras, compile, lint, type-check, run tests, validate config, validate artifacts/catalog, and run frontend generator tests. Scheduled publish should run only after the same quality gates or against a validated release artifact.

### C2. Factory Reset Is Too Destructive for a Boolean Workflow Input

**Evidence level:** Confirmed from workflow and docs mismatch.  
**Severity:** Critical.  
**Area:** DevOps, destructive operation safety.

The workflow exposes reset as a boolean input. When true, it can remove local output/state directories and recursively delete S3 archive data. Docs mention safer confirmation semantics such as `reset_confirm`, but the workflow uses a simpler boolean.

CLI `clean` and `reset` have more explicit prompts in some contexts, but CI reset is less safe. This can erase historical state and published archive data through a misclick.

**Fix:** Require exact typed confirmation such as `RESET-HUNTX-STATE`, create S3 backup/snapshot before deletion, add dry-run preview, restrict reset to manual workflow with environment protection, and log exactly what will be deleted.

### C3. GatherX `/get <format>` Has a Runtime Bug

**Evidence level:** Confirmed source-level finding.  
**Severity:** Critical.  
**Area:** Bot runtime, user-facing UX.

`src/huntx/bot/interactive.py` reportedly has `_send_format_to_user()` building `output_dir = DATA_DIR / "output"` while the module imports `paths` and does not define `DATA_DIR`. The `/get <format>` command and callback delivery path can therefore fail with `NameError`.

The existing bot tests do not call the failing method path, so this bug can survive despite test files existing.

**Fix:** Replace `DATA_DIR` with the correct injected or configured path. Add method-level tests for `/get npvt`, callback `get:b64sub`, missing output directory, empty artifacts, and user-friendly error behavior.

### C4. Generated Proxy Artifacts Are Committed to the Repository

**Evidence level:** Confirmed public/inventory evidence.  
**Severity:** Critical.  
**Area:** Repository hygiene, security, data governance.

`outputs/`, `outputs_dev/`, and `data_archive/` contain generated proxy/config artifacts, decoded JSON, Base64 subscriptions, dev outputs, and historical artifacts. CI commits generated outputs back to `main`.

Risks:

- Repository history grows quickly and becomes expensive to clone.
- Untrusted Telegram content becomes source-controlled.
- Decoded JSON and proxy remarks may contain sensitive comments or hidden payloads.
- The project mixes source code, generated products, and runtime state.
- Artifact diffs can obscure actual code changes.

**Fix:** Freeze output commits temporarily. Secret-scan the current tree and history. Move generated outputs to GitHub Releases, Pages artifacts, S3/object storage, or another artifact channel. Keep only small sanitized fixtures under `tests/fixtures/`.

---

## 5. High-Priority Findings

### H1. Documented GatherX Commands Are Not Implemented

Docs claim commands including `/protocols`, `/count`, `/status`, and `/ping`, but the implemented/registered command set centers on `/start`, `/help`, `/get`, `/latest`, `/formats`, `/setformat`, `/myinfo`, `/mute`, `/unmute`, and callbacks.

Some input reports differ on whether tests mention `/status`, but the consolidated issue is the same: docs, command registry, registered handlers, and tests must be generated from one source of truth.

**Fix:** Implement the missing commands or remove them from docs. Add command-contract tests comparing docs, `_BOT_COMMANDS`, handlers, help output, and Telegram command menu.

### H2. Configuration Validation Is Too Shallow

`SourceConfig` allows `telegram` and `telegram_user` blocks to be optional while `type` must be one of those values. `validate_config()` checks duplicate source IDs and route source references, but does not fully validate:

- `type="telegram"` requires `telegram` and forbids `telegram_user`.
- `type="telegram_user"` requires `telegram_user` and forbids `telegram`.
- `api_hash`, `session`, peer, route names, formats, destination modes, and tokens are non-empty and valid.
- Route formats exist in the registered format registry.
- Destination modes are enums.
- Environment expansion failures are fatal for required fields.

`env_expand` replaces missing `${VAR}` values with empty strings, allowing CI to appear healthy while doing little, skipping sources, or failing later with vague Telegram errors.

**Fix:** Add strict config validation and fail-fast errors with exact field names.

### H3. `ArtifactStore` Path Construction Is Not Safe Enough

`ArtifactStore.save_artifact()` and `save_output()` interpolate `route_name` and `format_id` into filesystem paths. Production currently uses safe names such as `all_sources`, but the API should be safe by construction.

**Fix:** Use `safe_component()` inside the store itself. Reject or sanitize `/`, `\`, `..`, empty names, long names, Unicode confusables, spaces if unsupported, and shell-like characters. Add path traversal tests.

### H4. Transform Can Loop Forever if State Writes Fail

`TransformPipeline.process_pending()` repeatedly calls `get_pending_files()` until no pending rows remain. It depends on `_flush_batch()` successfully adding records and updating file status. But `StateRepo.add_records_batch()` and `update_file_status_batch()` reportedly catch exceptions and log without re-raising.

If a status update fails, files remain pending and the loop can select them repeatedly until the outer workflow timeout.

**Fix:** Make batch write/status failures fatal to the transform phase, or return explicit success/failure and break with a clear error. Add tests simulating SQLite write failure.

### H5. Publish Tests Encode Weak Behavior as Success

Current publish behavior can treat a missing destination token as a logged skip and still return success if nothing failed. A test reportedly asserts this behavior.

That is acceptable for local/best-effort mode but unsafe for scheduled production where the operator expects publishing to happen.

**Fix:** Introduce modes:

- **Local/best-effort:** missing token warns and skips.
- **CI/production strict:** missing token fails publish phase.

Update tests to require strict-mode failure.

### H6. `docs/catalog.json` Is Stale and CI Does Not Regenerate It

`docs/catalog.json` reportedly says it was generated on 2026-02-16 and lists only five dev artifacts. The workflow runs HuntX, verifies/packages output, uploads artifacts, commits `outputs/` and `outputs_dev/`, and persists state, but does not run `scripts/generate_site_data.py`.

The static frontend can therefore show stale artifact metadata while backend outputs are changing.

**Fix:** Either run `scripts/generate_site_data.py` in CI and deploy/commit the generated docs artifacts intentionally, or stop committing frontend artifact data and generate it in a Pages deployment job.

### H7. `--no-deliver` Is Ambiguous

CLI `--no-deliver` skips post-run subscriber auto-delivery through `InteractiveBot.deliver_updates()`, but does not necessarily skip route publishing inside the orchestrator.

Users may interpret it as "do not publish to Telegram at all."

**Fix:** Rename or split flags:

- `--no-auto-deliver` for subscriber delivery.
- `--no-publish` for route destinations.
- `--dry-run` for no external side effects.

### H8. Secret Redaction Is Incomplete

The redaction filter masks Bot API token shapes and some key/value secrets, but reports say it does not fully cover `TELEGRAM_API_HASH`, `TELEGRAM_USER_SESSION`, `AWS_SESSION_TOKEN`, arbitrary session strings, and broader secret names. Workflow logs may also reveal S3 bucket names and operational identifiers.

**Fix:** Add comprehensive secret/session redaction snapshots. Treat Telethon session strings as account access secrets. Scan full tree and git history.

### H9. APK and Executable Filtering Is Too Shallow

Bot API and MTProto connectors reject APKs mostly by filename, extension, or reported MIME. Renamed APKs, ZIP containers, executable payloads, and misleading metadata can bypass this.

**Fix:** Add post-download magic-byte inspection, ZIP/APK structure checks, executable/script detection, maximum sizes, and tests for renamed APKs, APK MIME, ZIP-with-APK-like manifest, and corrupt archives.

### H10. MTProto Rate Limit Handling Is Not Explicit Enough

Telethon connector uses retry/reconnect patterns, but explicit `FloodWaitError` and Telegram RPC handling were not clearly found. Under scheduled multi-source scraping, rate limits are normal.

**Fix:** Catch `FloodWaitError`, respect wait duration, add per-source backoff, expose source health, and alert when a source yields zero messages for repeated runs.

### H11. Telegram Publisher Does Not Validate Bot API `ok`

`TelegramPublisher.publish()` returns decoded JSON after HTTP response but reportedly does not check `payload["ok"]`. Telegram usually returns non-2xx for many failures, but defensive code should still reject JSON `ok:false`.

**Fix:** Raise on `ok:false`, parse `retry_after`, and add retry/backoff tests.

### H12. Same-Second Published Hash Lookup Can Be Nondeterministic

`get_last_published_hash()` orders by `published_at DESC LIMIT 1`. Because `published_at` uses second-level timestamps, multiple publishes for the same key within one second can tie.

**Fix:** Order by `published_at DESC, id DESC LIMIT 1`, or use a monotonic sequence/created row ID as canonical ordering.

### H13. Repo-Level Output Export Is Not Fully Atomic

The project has a strong `atomic_write()` helper, but `Orchestrator._export_outputs()` and `_export_dev_outputs()` reportedly use direct `write_bytes()` / `write_text()` for repo-tracked `outputs/` and `outputs_dev/`.

**Fix:** Use `atomic_write()` for all exported files, including `_manifest.json`, `proxies.txt`, `proxies.json`, and `proxies_b64sub.txt`.

### H14. Frontend Catalog Publishes Internal State

`docs/catalog.json` reportedly includes `_manifest.json` as a downloadable dev artifact because `generate_site_data.py` blindly scans `outputs_dev`.

**Fix:** Exclude hidden/internal files by default: `_manifest.json`, SQLite files, logs, temp files, and state files.

### H15. Frontend Repository Links Point to the Wrong Repo

The frontend header/footer links reportedly point to `cyb3r-jak3/huntx`, not `AmirrezaFarnamTaheri/HUNTX`.

**Fix:** Update links or make repository URL configurable in `catalog.json`.

---

## 6. Pipeline, State, and Storage

Positive architecture:

- CLI entry point maps `huntx` to `huntx.cli.main:main`.
- CLI commands include `run`, `bot`, `clean`, and `reset`.
- `huntx run` loads config, validates, acquires a lock, creates orchestrator, runs phases, and optionally triggers subscriber delivery.
- Orchestrator has ingestion, transform, build/publish futures, export, and cleanup phases.
- Raw storage is content-addressed by SHA-256 and sharded by hash prefix.
- Artifact storage uses output/archive/internal directories.
- SQLite uses WAL and state tables for source state, seen files, records, and published artifacts.
- Transform batches pending files and uses batch DB writes.

Risks:

- Transform timeout can log and proceed to build/publish from available data, which is fine only if outputs are marked partial.
- SQLite migrations are ad hoc and should become versioned migrations with a schema version table.
- State schema uses `route_name` to store artifact keys such as `route:format`; rename to `artifact_key` or split into `route_name`, `format_id`, and `artifact_key`.
- Thread pools and SQLite connections may race if shared across threads.
- No disk quota enforcement for outputs or raw blobs.
- Raw blobs may not have cleanup of unused content.
- Missing S3 credentials can start from empty state and duplicate ingestion.

---

## 7. Telegram Ingestion and Publishing

### Bot API Connector

Strengths:

- Uses `getUpdates`.
- Tracks per-token update state.
- Has retry/backoff-like behavior.
- Filters media and document sizes.
- Rejects APK by extension/MIME-style checks.
- Warns that Bot API cannot read old channel history where the bot was not present.

Risks:

- APK rejection needs magic-byte and container validation.
- Backoff appears constant or limited rather than robust exponential.
- No full treatment for `.tar`, `.zip`, executable files, or disguised payloads.
- Text items and document items use different external ID conventions.

### MTProto Connector

Strengths:

- Uses Telethon `TelegramClient` with `StringSession`.
- Supports text and document passes.
- Uses thread-local clients.
- Filters document size and unwanted media.
- Better matches production config dominated by `telegram_user` sources.

Risks:

- No explicit `FloodWaitError` handling was confirmed.
- Possible batching/loop issue after first 100 text/document items needs local verification due raw extraction/indentation ambiguity.
- MTProto skips APKs before download, but still needs post-download content validation.
- Text/document external IDs differ from Bot API conventions.

### Publisher

Strengths:

- Uses changed-artifact detection.
- Skips unchanged hashes.
- Skips tiny empty ZIPs.
- Formats captions.
- Marks published after send.

Risks:

- Missing publish token logs and skips instead of failing in strict mode.
- Upload retry/backoff is incomplete.
- `ok:false` JSON may not be checked.
- Large artifacts may hit Telegram size/rate limits.
- Multipart boundary should be randomized and robust.

---

## 8. GatherX Bot

GatherX has real persistence and interaction code. It creates `bot_users`, registers users, stores `muted`, `default_format`, and `last_delivered_at`, collects output/archive files, sends through Telethon, and registers handlers.

Main problems:

- `/get <format>` can hit undefined `DATA_DIR`.
- `/protocols`, `/count`, `/status`, and `/ping` are documented but not consistently implemented/registered.
- `/get` without arguments opens a chooser/current preference view; docs may imply it downloads the default format immediately.
- Tests mostly exercise SQL/constants rather than actual `InteractiveBot` methods.
- No confirmed per-user rate limit or allowlist/admin mode.
- Anyone who DMs the bot may be able to register; this may be intended but must be explicit.
- `_latest`/delivery flows should cap file count/size and provide clear empty/error states.
- User preference updates may need row-level or transaction safety under concurrency.
- Running the bot with the same user session as ingestion may not be supported and should be documented.

Fixes:

- Repair path handling.
- Generate command docs from bot registry.
- Add method-level tests with fake DB/client/events/files.
- Add optional allowlist/admin mode.
- Add rate limiting.
- Add user-safe and operator-safe `/status`.
- Add privacy note and mute guidance in `/start`.

---

## 9. Formats, Parsers, and Output Building

Format handling is modular, but parser correctness needs much stronger testing.

Findings:

- `guess_format()` inspects extension, MIME, and first bytes. Unknown formats defaulting to `npvt` can misclassify binary formats.
- `npvt` extraction regex can over-capture trailing punctuation such as `)`, `]`, `.`, or `,` when URIs are embedded in prose.
- Base64 detection is heuristic: no spaces, no `://`, length threshold, then decode with padding. Needs bounded decode and invalid-input property tests.
- Invalid Base64 and malformed lines may be caught with broad exceptions, silently dropping records.
- Opaque/binary handlers such as OpenVPN-like bundles may preserve raw blobs rather than truly parse/validate them.
- Many format handlers such as `ehi`, `ovpn`, `hat`, `opaque_bundle`, and `npvtsub` need deeper malformed-input tests.
- Build phase writes decoded JSON, native outputs, and Base64 subscriptions but may rebuild all outputs every run.
- Outputs are not compressed by default.
- Deterministic ordering/golden snapshots are needed to reduce noisy diffs.

Fixes:

- Add parser adversarial corpus and Hypothesis/property tests.
- Trim common trailing delimiters from extracted URIs.
- Bound Base64 preview/decode lengths.
- Document opaque/binary formats as "detected, deduplicated, and bundled" rather than decoded/validated.
- Add central format registry metadata: supported extensions, MIME expectations, binary/text mode, parser support, output support, and known limitations.

---

## 10. Static Frontend and Catalog

Strengths:

- Static frontend has search, filters, sorting, dark mode, cards, copy link, toast feedback, loading, empty search, theme persistence, and cached catalog behavior.
- It uses a clear artifact repository concept.
- `isSafeArtifactPath()` / safe link checks reject URL schemes, path traversal, backslashes, and non-artifact prefixes in at least one component.
- Catalog entries include file name, path, size, type/ext, tags, modified timestamp, and short hash.

Risks:

- `docs/catalog.json` is stale and CI does not regenerate it.
- Catalog may include internal `_manifest.json`.
- Catalog caches in `localStorage` for one hour without schema/version validation.
- CDN dependencies from `esm.sh` and Tailwind CDN lack SRI/vendor pinning.
- Large catalogs may need pagination, virtualization, or sharding.
- Path safety exists in components, but generator-side schema validation and symlink handling are needed.
- Potential XSS risk exists if file names, tags, or metadata are rendered without escaping.
- Header/footer repo links may point to the wrong repository.
- Accessibility is incomplete: icons, forms, labels, focus states, contrast, and screen-reader feedback need review.
- No explicit user-friendly error state when `catalog.json` fails.

Fixes:

- Decide whether `docs/catalog.json` and `docs/artifacts/` are source-controlled Pages inputs or generated deploy outputs.
- Run generator in CI if using static catalog deployment.
- Add `schema_version`.
- Validate catalog before deploy and in frontend.
- Exclude internal files.
- Add freshness badges, Latest/Dev/Archive tabs, artifact age, counts, protocol/format tags, checksums, import instructions, safe previews, and large-download warnings.

---

## 11. CI/CD, DevOps, and Configuration

Findings:

- Workflow runs every two hours, while timeout is reported as 180 minutes. Slow runs can overlap/queue behind later scheduled runs.
- `cancel-in-progress` is false or not protective enough.
- Workflow has `contents: write` because it commits generated outputs; this should be isolated to the commit job and protected.
- It restores/persists S3 state and archive if configured.
- It installs runtime dependencies, not dev dependencies.
- It does not run frontend generator.
- It does not run unit/lint/type/format/security checks.
- Dependency management uses ranges and lacks a lockfile/security audit automation.
- `.gitignore` ignores runtime `data/`, `persist/`, logs, sessions, DB WAL/SHM, and caches, but not generated `outputs/`, `outputs_dev/`, `docs/catalog.json`, or `docs/artifacts/`.
- `.gitattributes` only has `* text=auto`, with no large/binary artifact policy.
- Docs mention systemd scripts, but their existence/behavior is unclear or unverified.

Fixes:

- Add workflow concurrency or reduce timeout below schedule interval.
- Split test/quality job from publish job.
- Add strict artifact policy.
- Add generated output retention and size caps.
- Add lockfile parity and dependency security checks.
- Add branch/environment protection for publish/reset jobs.

---

## 12. Security and Abuse Risks

High-priority security risks:

- Generated artifacts from untrusted Telegram content are committed and exposed.
- Secret redaction is incomplete.
- APK/executable filtering is bypassable by rename or misleading metadata.
- Boolean reset can delete S3 archive recursively.
- Bot may allow anyone to register by DM unless allowlist/admin mode is configured.
- Telethon session script prints reusable session string; docs must warn this equals account access.
- Source names, user IDs, chat IDs, and S3 bucket names may leak in logs.
- Static frontend catalog schema validation is not enforced before deployment.
- CDN dependencies introduce supply-chain risk.
- Ingested files are not malware-scanned.
- Legal/ToS risks exist around scraping and republishing proxy configurations from Telegram.

Security roadmap:

- Secret-scan repository and history.
- Stop committing untrusted artifacts to `main`.
- Complete redaction for token/session/hash/key patterns.
- Add MIME/magic executable filtering.
- Add bot rate limiting and optional allowlist.
- Protect reset/publish workflows.
- Validate frontend catalog.
- Use least-privilege S3 and GitHub permissions.
- Document safe handling of Telethon sessions and bot tokens.

---

## 13. Testing Strategy

The test suite appears broad by filename, but it is not enforced by the main workflow and several tests provide false confidence by testing SQL/constants instead of runtime methods.

Required P0/P1 tests:

- CI smoke gate: install dev deps, compile, pytest, Black, Flake8, mypy.
- Bot command contract: docs command table vs registry vs handlers.
- Bot `/get` regression for undefined path bug.
- Bot runtime tests with fake DB/client/events/output files.
- Publish strict-mode tests for missing token and Telegram `ok:false`.
- Config strictness tests for missing env vars, unsafe route names, unknown formats, invalid source blocks.
- Artifact path tests for `../`, slashes, backslashes, empty names, long names.
- Transform loop tests for failed status updates.
- MTProto >100 messages/documents and offset/batching tests.
- FloodWait/retry-after tests.
- APK bypass tests: renamed APK, MIME APK, ZIP/APK-like manifest.
- Malformed parser fuzzing: random bytes, huge lines, invalid Base64, corrupt ZIP.
- Golden output snapshots for deterministic artifacts.
- Catalog contract tests, schema validation, safe path enforcement.
- Frontend generator tests excluding `_manifest.json`.
- Static frontend Playwright/Cypress tests for search/filter/error states/XSS.
- Security regression tests for secret redaction and path traversal.
- Destructive command safety tests.

---

## 14. Documentation and Product Drift

Confirmed or likely documentation mismatches:

- README quickstart uses placeholder clone URL instead of actual repository.
- Manual `max_workers` defaults differ across user guide, workflow, env fallback, and CLI fallback.
- Docs mention `reset_confirm`; workflow exposes boolean `reset`.
- Docs say `/protocols`, `/count`, `/status`, and `/ping`; implementation does not consistently provide them.
- `/get` behavior in docs differs from chooser/default behavior.
- User guide/env variable names are outdated or inconsistent in places.
- `outputs_dev/README.md` says all-time cumulative, while workflow reset README says 48-hour rolling window.
- README claims many formats/protocols, but true support needs generated proof from registry/tests.
- Developer guide may mention systemd scripts that are absent or unverified.
- Telethon session setup docs need stronger secret-handling guidance.
- `--no-deliver` semantics need clearer wording.

Fixes:

- Generate command docs from bot registry.
- Generate format/protocol docs from registry/tests.
- Generate output docs from manifest.
- Document env vars in one table with required/optional/default/sensitive.
- Add safe local dry-run workflow.
- Add S3 setup with least-privilege IAM.
- Add architecture and state diagrams.
- Document artifact retention, generated-output policy, reset behavior, and recovery.

---

## 15. Cleanup and Repository Hygiene

Cleanup candidates:

- `outputs/`, `outputs_dev/`, and `data_archive/` generated artifacts.
- `outputs/verify_output.py` and `outputs/v2ray_test_config.json` unless deliberately kept as fixtures.
- `docs/catalog.json` and `docs/artifacts/` if they are generated deploy outputs rather than source.
- Internal `_manifest.json` in frontend artifact catalog.
- `src/huntx/cli/commands/run.py` if dead/unwired.
- Commented-out or unfinished sections in `scripts/verify_output.py`.
- Stale systemd references or missing deployment scripts.
- Inconsistent test names and duplicate/low-value tests.
- Unused CLI flags and env vars.
- Undefined/unreferenced sources/routes in production config.

Cleanup plan:

1. Freeze generated artifact commits.
2. Secret-scan current tree and history.
3. Move generated outputs to Releases/S3/Pages artifact storage.
4. Keep only sanitized fixtures in source.
5. Decide catalog deployment model.
6. Add `.gitignore` / `.gitattributes` / LFS or release policy accordingly.
7. Classify modules as active, experimental, generated, deprecated, or fixture.
8. Delete only after tests and workflow references confirm safety.

---

## 16. Refactor and Maintainability Roadmap

Recommended architecture work:

- Add `RuntimeOptions` / `PipelineOptions` shared by CLI, workflow, and docs.
- Separate phases into explicit services: `IngestService`, `TransformService`, `BuildService`, `PublishService`, `ExportService`.
- Replace global mutable path state with dependency-injected path/config objects.
- Introduce versioned DB migrations and schema version table.
- Define canonical models: `ProxyRecord`, `RawBlob`, `ArtifactKey`, `RouteOutput`, `PublishResult`, `RunHealth`.
- Make format handlers plugin-like and self-describing.
- Abstract storage layer for raw/artifact/state storage.
- Use one DB connection per worker or an explicit connection/session policy.
- Add structured logging and metrics.
- Make route publishing and subscriber delivery separate abstractions.
- Add dry-run services for integration tests.

---

## 17. Product and UX Roadmap

Product improvements:

- Stabilize GatherX core commands.
- Add source health status: last success, failures, messages fetched, files skipped, records extracted.
- Add `/status` with user-safe and operator-safe modes.
- Add admin controls: broadcast, maintenance mode, blocked users, allowlist.
- Add user preferences beyond default format: max file size, latest-only, protocols, mute windows.
- Add onboarding for formats/protocols in bot and frontend.
- Add subscription link generator for selected protocols/formats.
- Add legal/privacy notice for scraped proxy content and user-submitted sources.

Frontend improvements:

- Last generated / artifact age banner.
- Latest / Dev / Archive tabs.
- Format and protocol badges.
- Counts by format/protocol.
- Copy/import buttons with client-specific labels.
- Explicit fetch error state.
- Accessibility pass: landmarks, labels, `aria-live` toast, keyboard filters, visible focus.
- Mobile layout tests.
- Safe text preview with truncation.
- Large file warning and checksum display.

---

## 18. Prioritized Remediation Plan

### Fix First

1. Add CI quality gate before scheduled publish/commit.
2. Stop committing generated artifacts to `main` until policy and scanning are complete.
3. Add `reset_confirm`, backup, and protected manual reset.
4. Fix GatherX `/get` undefined path bug.
5. Implement or remove `/protocols`, `/count`, `/status`, `/ping`.
6. Add strict config validation and fail on missing critical env vars.
7. Sanitize/reject route and format path components in `ArtifactStore`.
8. Make transform DB write/status update failures fatal.
9. Add strict publish mode; missing token must fail CI/production.
10. Regenerate frontend catalog in CI or remove stale committed catalog/artifacts.
11. Exclude `_manifest.json` and internal runtime files from frontend artifacts.
12. Add complete secret/session redaction.
13. Add MIME/signature APK/executable filtering.
14. Add explicit FloodWait/retry handling.
15. Add bot command/runtime tests and parser/output golden tests.

### Highest ROI Improvements

1. CI quality and safety gates.
2. Bot command contract tests.
3. Generated artifact policy and storage migration.
4. Config fail-fast validation.
5. Artifact/catalog schema validation.
6. Frontend catalog generation in CI.
7. Single safe local fixture run.
8. Source health metrics.
9. Dependency/security automation.
10. Secret/history scan.

---

## 19. Verification Backlog

Before declaring HuntX healthy, verify:

- Exact commit SHA and current HEAD.
- Full local `pip install -e ".[dev]"`.
- `python -m compileall`.
- `pytest`.
- `black --check`.
- `flake8`.
- `mypy`.
- Frontend catalog generation.
- Static frontend browser tests.
- GitHub Actions static validation.
- Full generated artifact scan.
- Git history secret scan.
- Every file under `outputs/`, `outputs_dev/`, and `data_archive/`.
- All format handlers under `src/huntx/formats/`.
- Live/staging Telegram behavior with fake or disposable credentials.
- Telethon FloodWait and offset behavior.
- S3 restore/persist with disposable bucket.
- Systemd/deployment scripts.
- Browser XSS scan of catalog rendering.
- Artifact storage policy and retention.
- Whether GatherX should be public, allowlisted, or admin-only.
- Whether generated proxies can legally/ethically be republished.

---

## 20. Acceptance Criteria

HuntX should not be considered production-safe until:

- CI runs tests, lint, type checks, and artifact/schema checks before publish.
- Generated artifacts are no longer blindly committed to `main`.
- Destructive reset requires explicit confirmation and backup.
- Bot commands match docs and runtime tests.
- `/get` works for real output files and empty states.
- Config validation fails before runtime side effects.
- Missing publish tokens fail in strict mode.
- Frontend catalog is fresh, schema-validated, and excludes internal files.
- Telegram ingestion handles FloodWait and unsafe payloads.
- Secret redaction covers tokens, sessions, API hashes, and AWS credentials.
- Parser and output golden tests cover malformed and degraded inputs.
- Docs clearly explain dry-run/no-publish/no-deliver semantics.
- Source health, artifact freshness, and generated output policy are visible to operators and users.
