# Latest Protocol Subscriptions Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish persistent latest-100 subscriptions for each recognized protocol plus their complete aggregate on GitHub Pages.

**Architecture:** Reuse HUNTX's cumulative manifest and static snapshot publisher. A small URI-based generator creates immutable protocol files, Base64 mirrors and metadata; the assembler stages and catalogs them; the Pages validator rejects inconsistent publications.

**Tech Stack:** Python 3.11+, unittest/pytest, GitHub Actions, GitHub Pages.

## Global Constraints

No age cutoff or all-feed limit; at most 100 per protocol; no Others bucket. Preserve existing current-run, authenticated release feeds and cumulative history. Only valid supported proxy URIs are publishable. Alias variants share protocol families. Don't expose health claims for historical nodes. Preserve deterministic sort and bytes across repeat runs.

---

### Task 1: Generate historical protocol subscriptions

**Files:** Create `src/huntx/formats/latest_subscriptions.py`; test `tests/test_latest_subscriptions.py`.

**Interfaces:** Consume `dict[uri, first_seen]` and source timestamp. Produce `write_latest_subscriptions(destination, manifest, source_created_at) -> dict` and `validate_latest_subscriptions(directory) -> dict`.

- [x] **Step 1: Add focused failing tests:** exact 100 newest, no age cutoff, aliases, credentials, unknown URI schemes, Base64, union, deterministic replay, corruption detection.
- [x] **Step 2: Verify relevant failure:** initially `huntx.formats.latest_subscriptions` did not exist; importing the test fixture would fail.
- [x] **Step 3: Implement:** validate and classify supported URI schemes, select 100 per category, publish all files, assert counts and sha256.
- [ ] **Step 4: Verify focused pass:** `PYTHONPATH=src python -m pytest -q tests/test_latest_subscriptions.py` must pass.
- [ ] **Step 5: Run integration:** `PYTHONPATH=src python -m pytest -q tests/test_proxy_output_derivatives.py` must pass.
- [x] **Step 6: Commit:** feature and focused tests committed on the PR branch.

### Task 2: Integrate generator into cumulative publication

**Files:** Modify `scripts/assemble_generated_snapshot.py`, `tests/test_generated_output_publication.py`.

**Interfaces:** The assembler invokes `write_latest_subscriptions` after historical manifest compaction, then stages `outputs_dev/latest` at `docs/subscriptions/latest` and `docs/artifacts/dev/latest`.

- [x] **Step 1: Add failing integration assertions** for mirroring and indexed subscription entries.
- [x] **Step 2: Verify relevant failure:** no latest directory or catalog entries previously existed.
- [x] **Step 3: Implement:** stage both paths and add catalog metadata with exact size and SHA-256.
- [ ] **Step 4: Verify focused pass:** `PYTHONPATH=src python -m pytest -q tests/test_generated_output_publication.py`.
- [ ] **Step 5: Verify integration:** run `python scripts/assemble_generated_snapshot.py --help` and repository publisher checks.
- [x] **Step 6: Commit:** publisher integration committed on PR branch.

### Task 3: Validate static deployment and document endpoint contracts

**Files:** Modify `scripts/validate_pages_package.py`, `docs/SUBSCRIPTION_FORMATS.md`; tests `tests/test_latest_subscriptions.py`.

**Interfaces:** Pages validation checks both mirrors, source URI family, counts, aggregate union and catalog completeness.

- [x] **Step 1: Add regression test** rejecting publication after tampering either mirror.
- [x] **Step 2: Verify relevant failure:** previous validator did not inspect the latest subscription tree.
- [x] **Step 3: Implement:** fail closed on mirror mismatch, missing entries, tampered bytes and invalid feeds; document live URLs and historical trust.
- [ ] **Step 4: Verify focused pass:** `PYTHONPATH=src python -m pytest -q tests/test_latest_subscriptions.py`.
- [ ] **Step 5: Full suite:** `PYTHONPATH=src python -m pytest -q` plus publisher workflow CI.
- [x] **Step 6: Commit:** validation and docs committed on PR branch.

## Open decisions

None. The user approved the public endpoint layout, per-protocol retention, and aggregate behavior. GitHub CI is the remaining execution environment for full integration tests because this runtime cannot clone the public repository.
