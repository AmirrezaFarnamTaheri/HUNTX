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
`🇫🇷?`: the question mark always means *unverified hint*.

## Client remark contract

Production enables `HUNTX_REMARK_STYLE=evidence`. Example shapes:

```text
🇩🇪 VLESS-WS-TLS | edge.example.net:443 | AS64500 | DNS:OK | TCP:43ms
🇫🇷? TROJAN-WS | relay.example.net:443
🌐 HYSTERIA2 | hy.example.net:443
🌐 VLESS-WS-TLS | edge.example.net:443 | No.2
```

Names identify the protocol and actual destination. A single country flag
is enough for a known region, with no repeated ISO code; unknown geography
uses only the `🌐` globe, never the `ZZ` placeholder. A country flag without
`?` requires unexpired, attributed prefix geolocation evidence, while an
explicit source remark is marked with `?`. SHA hashes are never shown as
user-facing diagnostics. Only distinct configurations that would otherwise have identical
human-readable names get a short numeric ordinal; passwords, UUIDs and keys
are never displayed in tags.

**Deduplication is semantic but conservative.** Source remarks, query-parameter
ordering and equivalent supported share-link encodings do not create new
identities; different credentials, paths, TLS security, or other potentially
meaningful parameters always remain separate. The canonical identity remains
internal. Raw URI, Base64 subscription, Sing-box, Xray, Clash and NekoBox
variants derive from that same deduplicated feed.

`HUNTX_REMARK_TCP_PROBE=1` enables up to 2,500 short DNS/TCP observations
per production build, at most 24 concurrent workers and 1.5 seconds per
connection. The resolver must return a publicly routable address, which is
pinned for the connect; no proxy credentials are sent. These are observations
from the *publisher's vantage at publication*, not ICMP pings, successful
proxy-protocol authentication, or permanent availability claims. UDP-only
links do not get TCP success labels. When DNS/TCP measurement is missing, it
is not invented.

`DL:` and `UL:` labels require fresh **authenticated end-to-end throughput
measurement**. Hysteria2-configured up/down Mbps limits and guessed proxy
speeds must never masquerade as measured bandwidth. Without such evidence,
download and upload metrics are omitted rather than fabricated.

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

## DNS, TLS, transport, and protocol diagnostics

Production samples up to **24 distinct public endpoints per run**, rotating
deterministically by GitHub run ID and protocol so one highly replicated
source does not monopolize tests. Concurrency is capped at four and each
DNS/TCP/TLS operation is time-bounded. Results appear in
`network-diagnostics.json` beside source-health, endpoint-inventory and
proxy-retirement reports.

The layers have intentionally different meanings:

| Observation | What it proves | What it does not prove |
|---|---|---|
| DNS resolves public A/AAAA | A resolver supplied a currently usable public address | DNSSEC, authoritativeness, TTL, or healthy proxy |
| TCP connect | The pinned public TCP destination accepted a connection | TLS, UDP, credentials, routing, anonymity |
| Standard TLS verified handshake | CA/hostname-validated TLS handshake succeeded | REALITY, QUIC, WebSocket/gRPC upgrade, proxy authentication |
| REALITY / QUIC / UDP | Native protocol verification required | A TCP timeout is never a UDP protocol failure |
| Authenticated proxy session | Requires a separate actual proxy-protocol receipt | TLS/TCP alone never substitutes |
| Egress / traffic quality | Requires authenticated end-to-end routing evidence | Unsupported in the public endpoint sample |

Public destinations are pinned to their validated numeric addresses after
DNS resolution, blocking trivial rebinding to loopback, link-local, private,
documentation or cloud metadata addresses. Hostnames, raw IPs, source
credentials, SNI, raw TLS certificates and provider error strings are omitted
from the report. DNS results do not claim authoritative NXDOMAIN: the
standard resolver may not distinguish NXDOMAIN from NODATA.

TLS verification is **never silently disabled** for an insecure source link.
Certificates are checked against the declared SNI or the endpoint host.
A TLS or DNS failure remains recoverable, with a suggested next check;
REALITY/QUIC/WS/gRPC are marked unverified until protocol-aware, credential-
authenticated checks exist. The sample cannot establish global uptime,
jitter, packet loss, throughput, or 'dead forever'.

Other dimensions requiring real protocol-level instrumentation include
multi-vantage availability, resolver disagreements, DNSSEC, DNS TTLs and
CNAME history, IPv6 reachability by vantage, protocol auth outcomes,
QUIC ALPN, gRPC streams, WebSocket handshake status, TLS version/cipher
and certificate renewal trends, endpoint rotations, CDN edge drift, network
loss/jitter, throughput and sustainable egress. Track these as **unknown**
until a compatible test records timestamped evidence, never infer them from
remarks, ports or server banners.
