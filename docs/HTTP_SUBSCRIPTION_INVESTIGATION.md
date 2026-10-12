# Public HTTPS subscription investigation

HUNTX investigates public subscription feeds alongside the existing Telegram
sources. The HTTP inputs are **observations**, not independently verified
working VPN connections. The user-provided and researched source inventory is
kept in `configs/http_subscription_registry.json`; the active production
definitions are in `configs/config.prod.yaml`. Tests compare the two.

## Coverage and source trust

- **29 user-supplied endpoints**: Mosifree (temporary / FRAGMENT),
  ThomasJasperthecat, Barry-Far Sub1–5, zieng2, Masir Sefid,
  WhiteDNS/iampedi5 (including Mihomo), Anonymous, Zarazaex,
  MahsaNet MCI/MTN Sub1–4 and igareck Russian subscriptions.
- **5 independently researched public feeds**: morpheusadam/v2ray-config
  (mini bundle), fifthidea/sub (tiny plaintext), iboxz/free-v2ray-collector
  (mix), ebrasha/free-v2ray-public-list (main bundle), and
  Au1rxx/free-vpn-subscriptions (bounded verified base64 chunk).
- Sources are separated by unique `src_http_*` IDs, marked
  `required: false`, and carry explicit `discovered_from` /
  `approval_evidence`. Approval authorizes controlled inspection and
  syntactic acceptance; it is **not** a claim of end-to-end reachability,
  security, or operator honesty.
- Six invalid initial upstreams are recorded but disabled:
  `src_http_mahsa_mci_2`, `_mci_3`, `_mci_4`,
  `src_http_mahsa_mtn_3`, `_mtn_4` (empty files), and
  `src_http_igareck_2` (missing/404 on review). Re-enable only after
  confirming the target provides a nonempty subscription; do not delete
  history.

## Format contract

| HTTP response | HUNTX action |
|---|---|
| Raw mixed VLESS/VMess/SS/Trojan/etc. URIs | Parse, validate, deduplicate to canonical `npvt` / `npvtsub` |
| Base64-wrapped share links | Decode with strict base64 validation, then use the same canonical validator |
| Mihomo `proxies:` YAML | Convert only representable independent nodes; count unsupported/lossy entries |
| JSON list of share-link strings | Parse as candidate standalone URIs |
| Full JSON Xray profiles (Mosifree FRAGMENT) | Audit profile/outbound counts and dependency usage only; never flatten fragmentation/routing into a broken standalone node |
| HTML/error pages, malformed base64/JSON, zero usable nodes | Reject without changing the previous good artifact |

The normalized payload must contain valid standalone share URIs; the existing
`NpvtHandler` owns protocol-specific validation and global identity
deduplication. `dialer-proxy`, plugin, chained-routing and unsupported
transport features must not be silently dropped. Each feed is limited to
5 MiB, at most 9,000 imported nodes, and a 2–40 second network timeout.

## Native Go I/O and caching

The existing Go binary `cmd/huntx-engine` now implements `feed-fetch` for
source HTTP retrieval and conditional cache validation. Python retains
SQLite transaction/state ownership, source governance, and the format
normalizer; a whole-pipeline port is deliberately not attempted in this
integration because it would duplicate proven ordering and lease invariants.

Source URLs and conditional cache validators pass to the native Go worker in
a bounded stdin JSON envelope rather than process arguments. Cached bodies
are bound to the URL fingerprint as well as the normalized SHA-256 digest:
an edited source URL cannot reuse an unrelated upstream cache or ETag.

The Go network boundary enforces an exact public HTTPS host allowlist,
rejects redirects, does **not** honor proxy environment variables, resolves
and connects only to permitted public addresses (blocking private,
link-local and special-purpose ranges), limits response bytes and timeout,
and returns only a bounded JSON/base64 response envelope. Fetch errors
must not reveal subscription URLs or embedded node credentials.

Build the Go worker locally before running the canonical CLI:

```sh
mkdir -p .bin
go build -o .bin/huntx-engine ./cmd/huntx-engine
```

Production workflows already build the same Go binary. HUNTX can also
resolve it via `HUNTX_ENGINE_BIN` or `PATH`. No shell is involved.

A conditional `If-None-Match` / `If-Modified-Since` request is permitted
only when the prior normalized SHA-256 maps to a verified, available
content-addressed blob. A 304 then revalidates that local payload rather
than trusting an absent or corrupt cache. Cache metadata (ETag, timestamps,
hashes and counts), not proxy credentials, is kept in source state. The
first/last seen time, last changed time, success total, failure streak,
last failure type and node-count delta are tracked separately.

Feed retrieval reliability is reported separately from proxy reachability.
A 95% Wilson lower bound quantifies observed retrieval success with sample
size awareness, and last-success age produces recent/degraded/stale states.
One successful fetch does not imply a reliable VPN endpoint. Timeout and
network failures preserve previously validated content and increment only
the optional source failure counters.

Mihomo parsing refuses unknown option keys, dangerous YAML aliases, excessive
nesting and oversized structured input. Only independently representable
proxy settings are converted into share URIs; ECH, mTLS, dialer chains and
other unportable policy dependencies are skipped and counted.

## Reliability and historical guarantees

1. Source-level failures are isolated: they increment optional-source
   failures, preserve the existing valid raw observation, and do not
   prevent successful Telegram ingestion. Required Telegram failures retain
   their existing release eligibility gate.
2. A changed feed replaces the prior observation by the same stable
   `external_id`. HUNTX deactivates prior records transactionally before
   replacing them, and the transform pipeline validates the replacement.
3. A successfully revalidated *unchanged* feed may refresh `ingested_at`
   only for the same previously **processed** observation, never for
   pending, failed, ignored, retired or quarantined records.
4. Existing build queries require `r.is_active = 1`; source trust is
   checked at export. Scoring assigns zero to explicit failed probes or
   revoked/retired/inactive proxies, regardless of historical latency.
5. Source health reports expose IDs, counts, parser kind, cache state and
   error classes, never credential-bearing URLs. `syntax_validated` is
   not an active transport handshake; upstream marketing claims like
   `DNSOK`, country flags or `GPT+` are not verified evidence.
6. Subscriber remark numbering is unchanged by default for compatibility.
   `HUNTX_REMARK_STYLE=stable` opts into protocol/transport/security
   descriptors with a deterministic 48-bit hashed suffix; it does not
   fabricate a region, speed or quality grade.

## References

- Hiddify official: https://github.com/hiddify/hiddify-app
- Go HTTP redirect contract: https://pkg.go.dev/net/http#Client
- Go netip caution (`IsGlobalUnicast` alone does not exclude private
  networks): https://pkg.go.dev/net/netip#Addr.IsGlobalUnicast
- Xray official JSON configuration: https://xtls.github.io/en/config/
- Mihomo supported proxy fields: https://wiki.metacubex.one/en/config/proxies/
- Research repositories: https://github.com/morpheusadam/v2ray-config,
  https://github.com/fifthidea/sub,
  https://github.com/iboxz/free-v2ray-collector,
  https://github.com/ebrasha/free-v2ray-public-list,
  https://github.com/Au1rxx/free-vpn-subscriptions

## Acceptance checks

`python -m pytest -q tests/test_http_subscription_sources.py`;
`python -m pytest -q -m "not perf"`;
`python -m mypy src/huntx`;
`go test -race ./...`;
`go vet ./...`;
`gofmt -l .` must be empty.

Production functionality additionally requires access to real upstreams from
its deployment network. A green PR CI validates contracts, *not* access
through MCI/MTN or real client imports.
