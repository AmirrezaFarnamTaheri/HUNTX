# HUNTX: proxy health, evidence, lifecycle and source quality

This document distinguishes feed retrieval from an actually working authenticated
proxy. A valid URI, reachable TCP port, TLS handshake and successful
proxy-protocol negotiation are separate evidence stages; their numerical scores
must not be conflated.

## Evidence hierarchy

| Layer | Sufficient evidence | What it does **not** establish |
|---|---|---|
| Public subscription | successful bounded HTTPS fetch, parser acceptance, valid URI syntax | live proxy, endpoint operator, usable credentials |
| Endpoint reachability | bounded DNS resolution and TCP connect to approved public IP | successful TLS, proxy authentication, outbound internet |
| TLS handshake | successful TLS with appropriate peer verification and negotiated parameters | proxy authentication or routing rules |
| Authenticated proxy | successful protocol-authenticated request through the proxy, timed and recorded from a specified vantage | performance or availability in a different geography or carrier |
| Operator/country metadata | explicit independently verified operator/geo evidence | network performance or suitability without a relevant vantage |

**Publishing policy:** A source that repeatedly returns valid links is not
"100% alive." Only a fresh authenticated protocol probe can earn a verified
grade or recommendation. An explicitly failed probe receives no recommendation.
Synthetic numeric estimates remain available for compatibility but are not
verified grades.

## Historical source reliability and scheduling

`source_state.retrieval_history` records the last 64 observed retrieval
attempts from the previous 30 days. It contains timestamps, bool outcomes,
accepted-node counts and cache-revalidation flags—**no URLs, credentials or raw
proxy material**. Lifetime counters are kept for longer-term observation, but
the source rank uses the recent 95% Wilson lower bound and staleness penalties.
Unobserved sources remain eligible for an exploration slot; a failure does not
permanently exclude a source. Source ranking is evidence about *HTTP retrieval*
only, never proxy connectivity.

State lookups use one SQLite connection with bounded batches of 400 IDs.
Optional public subscriptions are fetched separately from the Telegram LIFO
window worker. When concurrency > 1, one worker serves the Telegram window
queue immediately; with a single worker, direct feeds and Telegram windows
run cooperatively under bounded timeouts. This prevents a slow feed from
blocking older Telegram history.

An HTTP 304 is accepted only with a URL-bound, SHA-256-verified cached body.
A successful unchanged fetch refreshes freshness only for an already processed
observation; it never rewrites a failed or inactive record. A changed feed
supersedes the old observation in the same state transaction. A failed fetch
preserves the last-good content without marking it as newly verified.

## Proxy lifecycle database and nonrevivability

SQLite schema version **12** creates:

- `proxy_lifecycle`: keyed by canonical SHA-256 identity + record type.
  Includes first/last observation time, last authenticated success,
  successes/failures, consecutive failure streak, last probe status and
  a machine-readable terminal reason.
- `proxy_probe_history`: append-only, idempotent authenticated probe receipts
  with vantage identifier, timestamp, outcome and measured latency.

Lifecycle stages: `discovered → active → degraded → suspect`. An explicit
policy decision may terminalize a hash as `dead`, `revoked` or `archived`.
**A source reposting the same URI cannot clear a terminal status**; neither a
passive observation nor a later reported success revives it. A material change
to a configuration changes its canonical identity and may be evaluated as a
new proxy. Non-terminal failures recover only after a new authenticated
protocol success; an out-of-order delayed success cannot override a newer
failure. Probe receipts are idempotent and must not be reused for another hash.

Both compatibility and secure governed SQL build queries exclude terminal
identities, independently of source provenance. Active record filtering and
source-scoped observation IDs remain mandatory. A terminal lifecycle decision
does not erase the historical observation or claim a new probe was performed.

`record_authenticated_probe` is a local persistence API; **nothing in this
change claims Go TCP probing now authenticates proxy protocols**. A future
vantage adapter must provide real authenticated evidence and a replay-resistant
receipt, not raw public feed metadata.

## Remarks and source provenance

The default subscriber remark retains ordinal names for existing compatibility.
`HUNTX_REMARK_STYLE=stable` generates a deterministic truncated SHA-256
identity and transport/security qualifiers, without gratuitous unverified
countries, grades or fake "stable X days" labels. Metadata-rich remarks display
an operator only if `operator_verified=True` with an explicit operator value;
a health grade only if `probe_kind=protocol_authenticated`,
`probe_ok=True` and `probe_age_seconds <= 3600`; a failed probe overrides
declared marketing grades. Ordinary network latency alone does not prove
authenticated proxy functionality. VMess remarks are stored in the `ps`
field; other share links use their fragment. No proxy secrets are exposed in
remarks.

## Native Go boundaries

The Go `subfeed` HTTP worker owns DNS resolution, public-address checks,
redirect refusal, bounded response bytes, 32-KiB response headers, total
timeouts, conditional cache fetches, and sanitization of errors to avoid
leaking credential-bearing subscription URLs. Additional IPv6 special-purpose
and tunneling ranges are excluded. Its HTTP transport does not honor proxy
environment variables. Go health scoring applies the same metric clamping,
security normalization, carrier matching and verified-evidence taxonomy as
Python compatibility scoring.

Do **not** port SQLite writer ownership, state transactions, Telegram leases
or release publication to a second Go writer just to remove Python. A separate
Go state owner without a validated cutover protocol would introduce a
split-brain risk. The existing Go native fetch/scoring functions are used
where their correctness boundaries are clear. Wider parser/formatter porting
requires differential test vectors for every supported protocol, credentials,
transport and helper-outbound dependency before substituting the Python
canonical validator.

## Acceptance and known limits

Run `go test -race ./...`, `go vet ./...`, `gofmt -l .`,
`python -m pytest -q -m "not perf"`, `python -m flake8 src/huntx tests scripts`,
`python -m mypy src/huntx`, and the frontend/deployment CI jobs.
The tests exercise migrations, source identity, stale health, source-ranking
fairness, probe receipt idempotence, nonrevivable lifecycle, secure-export
gates and Go public network restrictions. The production service still needs
real device/client imports, source availability from different carriers, and
authenticated protocol checks from approved vantage locations; PR CI alone
cannot certify those outcomes.
