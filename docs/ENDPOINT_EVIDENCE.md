# Endpoint evidence, rich remarks and retirement controls

HUNTX separates **proxy configurations**, **network endpoints**, **source
availability**, **TCP reachability**, **proxy-protocol authentication** and
**geographical or ASN attribution**. These are different claims and must not
be substituted for one another.

## What the refreshed pipeline collects

- Protocol, parsed transport, TLS/REALITY mode, normalized host/port and
  stable endpoint identity without exposing a proxy's login/token.
- IPv4/IPv6 literal classification and optional offline CIDR prefix attribution
  (ASN, AS organization, CDN operator, country estimate and anycast status).
- An immutable provenance label and expiry with every prefix attribution.
  Hostnames remain unresolved until a separate, validated DNS observation.
  Generic TLDs and upstream tags are never accepted as verified IP geography.
- TCP-only latency carries `probe_kind=tcp_connect`, observed/expiry times
  and `probe_authenticated=false`. UDP-only links are not failed by a TCP test.
- A read-only corpus inventory across **up to 50,000** active, processed NPVT
  records (including historical observations), aggregating protocol, transport,
  TLS, host family, endpoint duplication and metadata coverage.
- The existing source-health report remains separate from the new endpoint
  inventory and proxy-lifecycle audit. All three are retained in a
  30-day diagnostics artifact.

## Optional CIDR intelligence format

Set `HUNTX_NETWORK_INTELLIGENCE_PATH` to an operator-supplied JSON file:

```json
{
  "schema_version": 1,
  "provider": "trusted-operator-data-v1",
  "observed_at": 1800000000,
  "expires_at": 1800086400,
  "prefixes": [
    {
      "cidr": "203.0.114.0/24",
      "asn": 64500,
      "as_org": "Example Network",
      "country_code": "DE",
      "anycast": false
    }
  ]
}
```

This is a **format example**, not an actual allocation or ASN claim.
The loader refuses malformed/private prefixes, duplicate keys, over-broad
networks, non-canonical CIDRs, oversized files, future timestamps and
stale evidence. No automatic remote GeoIP/ASN calls are performed during
ingestion. Never mix routing location and country of corporate registration.
Anycast location is always unknown without vantage-specific measurement.

No dataset means **unknown ASN, CDN and verified location**, not fabricated
enrichment. Source-supplied country remarks may appear in rich tags as
`🇫🇷? FR`: the question mark always means *unverified hint*.

## Client remark contract

Production enables `HUNTX_REMARK_STYLE=evidence`. Example shapes:

```text
🇩🇪 DE | VLESS-WS-TLS | AS64500 | d4e6b3ca10
🇫🇷? FR | TROJAN | 9afac3a901
🌐 ZZ | HYSTERIA2 | 2fbb7d0922
```

A flag without a question mark requires unexpired prefix geolocation
evidence from the configured snapshot; if only source text is available it
is a question-marked hint. TLS, transport and ASN are parsed/attributed,
and stable digest suffixes disambiguate independent proxy credentials.
Never add fake health stars, made-up speeds or provider/operator labels
from arbitrary upstream text.

VMess uses its `ps` field. URI-based schemes percent-encode the fragment
for broad client compatibility. The decoded publisher dashboard uses the
same display tag as imported subscriptions. Set
`HUNTX_REMARK_STYLE=legacy` to restore the historical ordinal tags.

## Detect and remove dead proxies safely

**No finite series of network failures proves an endpoint is dead forever.**
The `proxy_lifecycle` ledger already provides explicit, irreversible
`dead`, `revoked` and `archived` policy decisions. Those identities
are excluded from both ordinary and governed outputs, even after
rediscovery through another source.

To prevent repeated *verified* failures polluting current outputs without
irreversible loss, HUNTX suppresses a `suspect` identity only when it has:

1. At least **six consecutive authenticated protocol failures**;
2. Failed observations from **two or more vantage IDs**;
3. Failed observations spanning **at least 24 hours**;
4. A most recent authenticated failure within **seven days**;
5. No newer authenticated success restoring it to `active`.

Suppression is temporary, not a terminal decision. Stale failures age out,
and a fresh authenticated success restores the candidate. A local TCP
handshake, UDP/TCP mismatch, one vantage, single-run DNS timeout, and
missing/invalid runtime worker count as **no authenticated failure evidence**.

The `proxy-retirements.json` report shows tracked identities, permanently
excluded identities, temporarily suppressed candidates, insufficiently
supported suspects, and short fingerprints for re-testing. It contains no
proxy URI or credential.

If verified credential revocation or an explicit policy decision is
available, operators can use the existing
`huntx.state.proxy_lifecycle.terminalize_proxy` transaction with a
machine-readable reason code; do not invoke it automatically on
transient error counters. Historical records remain available for audit and
diagnosis even when excluded from the published feed.

Run diagnostics manually with a local state checkpoint:

```bash
python scripts/report_source_health.py --config configs/config.prod.yaml --summary persist/data/logs/run-summary.json --db persist/state.db --output persist/data/logs/source-health.json
python scripts/report_endpoint_inventory.py --db persist/state.db --max-records 50000 --output persist/data/logs/endpoint-inventory.json
python scripts/report_proxy_retirements.py --db persist/state.db --output persist/data/logs/proxy-retirements.json
```

HUNTX does not currently collect authenticated multi-vantage sessions for
every published proxy. Consequently **no specific proxy may be labelled
permanently dead solely from the available production TCP tests**. Reported
metadata are observations, not a guarantee of availability.
