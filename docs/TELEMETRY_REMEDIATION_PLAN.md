# HUNTX telemetry remediation plan

**Scope:** correct the live dashboard's telemetry provenance and unknown/latency states, add regression protection, and keep the browser, Python producer, Go publisher, and Pages workflows on one generation.

**Status:** implemented in the working tree; verification is recorded below. This document is the source-backed remediation map requested for the change. It does not add a second runtime path or invent live-probe data.

## Contract

The published Pages artifact is one generation:

```text
verified dist
  -> Go site-data (catalog.json + release artifacts)
  -> Python telemetry-only generation (data.js from the same outputs + catalog)
  -> upload-pages-artifact
  -> deploy-pages
```

The browser contract is:

- `catalog.json` and the decoded artifact remain checksum-verified with Web Crypto SHA-256.
- `data.js` is usable as telemetry only when its `INGEST_STATS.generated_at` represents the same instant as `catalog.generated_at`.
- A live decoded record is rendered from configuration fields, then enriched only from a same-generation telemetry record.
- A record with no measurement stays unmeasured; a record with no address is not turned into a loopback endpoint.
- `health_grade` and `pca_score` from the producer take precedence over a frontend latency approximation.
- `ZZ` is unresolved geography, not a known region.

## Fix map

| Fix | Implementation | Contract protected by | Verification |
|---|---|---|---|
| Same-generation telemetry | `.github/workflows/huntx.yml` and `.github/workflows/publish-generated-outputs.yml` call `generate_dashboard_data()` after Go `site-data` and before Pages upload. `scripts/generate_site_data.py` reuses the supplied verified catalog and current output directories. | The Go catalog and Python `data.js` are produced from the same run. | `tests/test_frontend_delivery.py::test_primary_pages_workflow_generates_telemetry_before_upload`, `test_publish_workflow_uses_telemetry_only_entry_point`, `test_dashboard_only_generator_reuses_the_verified_catalog` |
| Live artifact does not discard telemetry | `docs/assets/js/app.js::loadLiveData()` imports the sidecar, compares generation instants, indexes telemetry by stable raw URI/fallback identity, and merges measurement fields. | A verified decoded artifact cannot silently erase the telemetry generated beside it. | `tests/frontend_runtime.test.mjs::live artifact mapping retains same-generation telemetry` |
| Timestamp representation | `docs/assets/js/app.js::isSameGeneration()` compares parsed instants, so `Z` and `+00:00` RFC3339 spellings of the same timestamp match. | Publisher and browser do not disagree over formatting. | `tests/frontend_runtime.test.mjs::generation timestamps compare by instant across RFC3339 spellings` |
| `raw_uri` contract | `normalizeProxyRecord()` and fallback loading expose both `raw` and `raw_uri`. | Feed, copy, QR, and export paths can consume the same generated field. | `tests/frontend_runtime.test.mjs::bundled fallback normalizes raw_uri into the raw feed contract` |
| Health parity | `getHealthScore()` consumes published `health_grade` and `pca_score`; frontend latency grading remains only a legacy fallback. | Producer grades and PCA scores are not recomputed or contradicted by the UI. | `tests/frontend_runtime.test.mjs::published health grade wins over the frontend latency approximation` |
| Unknown geography | `summarizeRegions()` excludes `ZZ` from known-region counts/ranking and reports unresolved nodes separately. | Unknown nodes cannot consume a real-region slot. | `tests/frontend_runtime.test.mjs::unknown geography is reported separately from known regions` |
| Invalid decoded entries | Live mapping rejects entries without `address` instead of substituting `127.0.0.1`. | Unusable rows do not become selectable endpoints. | The live-path regression fixture exercises the mapping boundary; browser test suite covers the rendered flow. |
| Honest unavailable state | The status pill says telemetry is unavailable when the generation cannot be matched; the diagnostics badge says `SNAPSHOT TELEMETRY` only for a same-generation sidecar. | “Integrity verified” is not misread as connectivity or telemetry verification. | Browser verification below. |

## Authoritative sources

- **Web Crypto SHA-256:** MDN documents `SubtleCrypto.digest()` and the supported `SHA-256` algorithm: <https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest>
- **Node.js focused test runner:** the Node.js documentation describes `node --test`, test files, and the stable test runner: <https://nodejs.org/api/test.html>
- **GitHub Actions environment and step syntax:** GitHub documents that step-level `env` values are available to the step and override less-specific values: <https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#env>
- **GitHub Pages artifact/deploy contract:** GitHub documents the build artifact upload and a deploy job that needs the build job, has `pages: write` and `id-token: write`, and uses the `github-pages` environment: <https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages>
- **Python URL timeouts:** Python documents `urllib.request.urlopen(url, data=None, timeout=...)` and states that the timeout applies to blocking connection operations: <https://docs.python.org/3/library/urllib.request.html>
- **Python concurrent probes:** Python documents `Executor.map()` and `ThreadPoolExecutor` as concurrent execution with a bounded worker pool: <https://docs.python.org/3/library/concurrent.futures.html>

## Deliberately not claimed

- SHA-256 verification proves artifact identity, not node reachability, latency, carrier, or country.
- The `huntx-probe` fleet is optional and has no static Pages WebSocket receiver in this repository. No live loss value is fabricated.
- The local Windows resolver is impaired, so local probe drop rates are not evidence that remote nodes are dead.
- The plan does not replace GeoIP or TCP semantics; it makes the producer's existing measurements travel with the same published generation.

## Verification commands

```text
node --test tests/frontend_runtime.test.mjs
# 22 passed

node_modules/.bin/playwright test --reporter=line
# 21 passed

python -m pytest -q -m "not perf" --strict-config --strict-markers \
  -p no:cacheprovider -p pytest_asyncio.plugin
# 1074 passed, 1 skipped, 4 deselected, 3 xfailed, 60 subtests passed

go test ./...
# passed

python scripts/update_frontend.py --check
# passed

./node_modules/.bin/eslint docs/assets/js/app.js tests/frontend_runtime.test.mjs
# passed

.venv/Scripts/python.exe -m flake8 scripts/generate_site_data.py tests/test_frontend_delivery.py --count --statistics
# 0
```

`mypy src/huntx` passed. Running mypy directly against `scripts/generate_site_data.py` still reports the same ten pre-existing `var-annotated` findings present in `HEAD`; this change did not add them. Black likewise reports the same pre-existing formatting delta in the two files, so no unrelated whole-file reformat was applied.

The committed generated snapshot was not regenerated in this change: generated artifacts are produced by the publication workflows, and the repository's contract forbids hand-editing them. The first real run of the updated workflow will publish a new `data.js` alongside its same-generation `catalog.json`.
