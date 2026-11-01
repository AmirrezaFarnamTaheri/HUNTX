# PR 160: merge, connection identity and publication review

Reviewed 23 October 2026 against main `e909fa93a98720af6052458ca59dfb550b687739` and PR head `60854853bedda048dde9ce04d38dca5b34de1758`.

## Confirmed defects and corrections

- GitHub reported `mergeable_state=dirty`. Seven files conflicted. The merge retains current main's HTTP subscription ingestion and accounting, worker fairness, independent client-node feeds, full-profile compatibility URLs, release ownership/rollback, semantic deduplication, and delivery/lifecycle schema migrations. It reapplies the PR's shared VMess contract and class-owned resilient runtime on that base.
- The original PR head cannot collect the Python suite: `optimized_orchestrator` imports `telegram_account_key` from a file that does not define it. The resulting initial import error cascades into collection errors. This is a real integration regression; the old description's two-baseline-failures claim does not describe this head. Current main passes 1,426 non-performance tests in the same environment.
- Shared VMess decoding now removes display fragments, rejects non-object and nonportable JSON, accepts standard/URL-safe base64, and uses one compact, sorted UTF-8 encoder. Snapshot assembly imports the runtime remark/identity functions rather than maintaining another implementation. VMess output names reside in `ps`; old source fragments are removed under current main's publication contract.
- URI-text identity missed equivalent client defaults, boolean aliases, numeric VMess fields and alternate encodings. Typed identity normalizes modeled connection settings while preserving unknown extensions and repeated parameters. Credentials, security, transport, paths and unknown options remain independent. Each client serializer also deduplicates the connection objects it actually emits, excluding presentation names from that key.
- On the checked-in production snapshot: 6,141 URI entries, zero old HUNTX-key duplicates, but 1,245 repeated parsed client configurations. New loss-aware URI identity removes 856 equivalent entries. Rebuilt Sing-box (4,848 nodes), Xray (3,235), NekoBox (4,848), and Clash (4,809) each contain zero duplicate serialized connection objects. Counts differ because format support and fidelity rules differ. These are offline conversion measurements, not claims that these nodes are live.
- Schema v13 rekeys proxy observation identities, retains each source observation, preserves verdict expiry, migrates probe-history foreign keys, and conservatively preserves explicit retirement. Publication artifact receipts are unchanged. Reopening does not repeat migration.
- Exact legacy ownership includes Clash and full-profile derivatives alongside raw/base64/JSON products. Governed production still uses the existing manifest exporter and its rollback/compatibility aliases.
- Country hints no longer append `?` to flags. Hint provenance remains metadata. Labels retain protocol/transport, safe endpoint, genuinely measured DNS/latency and ordinal disambiguation rather than exposing UUIDs or hashes. The dashboard continues to use the published name.
- Resilient timeout helpers bind correctly as instance methods. The moved runtime retains current main's worker reservation settings and optional-source accounting. Cleanup restores configuration and source lookup even when closing a worker fails. Strict Telegram peer resolution remains class-owned; compatibility aliases remain available.

## Generated diagnostic file

`.statamcp/debug/traces.jsonl` was first added by merge commit `6085485`. It contains 183 JSONL records / 74,519 bytes: initialization, initialization notifications, tools listing, resource listing and resource-template listing. Attributes contain method/protocol names and request IDs; envelopes contain timestamps, process and trace/span identifiers. No tool arguments/results or credential-pattern matches were found. This does not prove universal absence of secrets. No application reference or diagnostic feature depends on this file. It is deleted from the resulting PR diff, and `.statamcp/debug/` is ignored. Existing history is not rewritten.

## Production proxy health gate

The production workflow installs checksum-pinned Sing-box v1.14.3 and enables `HUNTX_REQUIRE_PROXY_HEALTH=1`. URI/base64 handlers share the gate before deriving client exports. Each semantic identity is tested once per sweep, with bounded concurrency, per-node timeout, total budget, temporary credential files, suppressed engine output and deterministic cleanup.

Each probe process has exactly one selected proxy outbound and no direct fallback. A usable node must carry a certificate-verified HTTPS request to an expected empty-204 endpoint. A second independent endpoint is attempted on failure. DNS resolution, an open TCP port, target redirects, wrong status/body, TLS failure, malformed proof, stale results, unsupported configurations, worker errors and untested budget residue cannot authorize a node. Unmodeled options are conservatively excluded when their exact connection cannot be attested. A separate local-only engine bootstrap fails the build on missing/broken infrastructure rather than calling an empty sweep successful.

Successful proof expires after five minutes. This is a publisher-vantage, point-in-time usability check; it cannot guarantee future availability or reachability on every user's network. Failure means not currently publishable, not permanent death. Opaque archives and all-time dev history remain historical material rather than a verified live-node feed. Outside the production workflow, explicitly enable the gate with `HUNTX_REQUIRE_PROXY_HEALTH=1`; set `HUNTX_SINGBOX_BINARY` when the engine is not on PATH.

## Validation and limits

- Current main baseline: 1,426 Python tests passed, four performance tests deselected, 64 subtests passed.
- Updated full suite: 1,491 passed before the final dormant-TLS and boolean-alias regressions; final results are recorded in the PR description.
- Targeted identity, health gate, migration, serializers and build checks: 92 passed before the final two identity regressions.
- Python compileall, flake8 and mypy pass; JavaScript lint passes; all 88 frontend unit tests pass under local Node 24 with `node --test` (Node 24 removed the repository command's `--experimental-default-type=module` option; CI uses Node 22).
- The pinned Sing-box binary was downloaded and checksum-verified, and accepts the generated probe configuration with `sing-box check`. This execution sandbox denies the netlink socket needed to start the engine; the infrastructure preflight correctly blocks publication. Mocked tests cover authenticated success/failure, TLS checking, response checking, duplicate checks and cleanup. A successful live-network probe sweep was not performed here.
- Go/Docker/Helm/browser and dependency-audit acceptance must come from GitHub's complete workflow matrix; local Python/JS results and CodeRabbit status are not substitutes.


## GitHub validation follow-up

Run 39942225319 passed Python, dependency audit, workflow syntax and deployment manifests. Go race tests passed, but govulncheck correctly rejected the existing Go 1.26.9 toolchain for GO-2026-6809 (crypto/x509; fixed in 1.26.10). Both module minimum versions and the digest-pinned Docker builders are updated to 1.26.10. The new image manifest digest was independently matched against the Docker registry and docker-library/repo-info. This is a baseline toolchain defect exposed by the full matrix, not an application test regression.
