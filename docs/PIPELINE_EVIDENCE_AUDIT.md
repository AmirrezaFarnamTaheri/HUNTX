# HUNTX: evidence integrity and independent classification

An Actions success is **not** proof of a new release, Telegram activity, or a
working authenticated proxy. A valid no-release verdict preserves the previously
published snapshot, timestamp and state. Check the current-run release receipt
before claiming a new generation was published.

## Telegram independence

MTProto rate limits, inaccessible channels, disconnections, and valid empty
scans are availability signals. The separate activity gate reports them as
rate_limited, unavailable, completed_empty, not_configured or
no_observed_ingestion and remains nonfatal. It reports verified_activity only
for completed scans with coherent source and message evidence. Malformed data
and cross-source identity contradictions remain integrity failures.

Production opts in to HUNTX_TELEGRAM_RETRY_RELEASE=1. This permits a strictly
retry_wait-only Telegram backlog to coexist with current HTTP-derived output,
provided that current parsed/audited HTTP evidence includes nonzero nodes and
the global ingestion budget was not exhausted. Other pending, leased, partial
or unreadable queue state still blocks release. Importantly, the existing
authenticated-proxy checks, output ownership, manifest verification, release
receipt and publisher eligibility checks are **not** bypassed. No Telegram
cursor is advanced and no Telegram source is declared scanned just because
HTTP succeeded. Disable the option to restore the strict backlog policy.

## Evidence stages

The pipeline evidence audit enumerates 18 stages: source_registry,
telegram_ingestion, http_ingestion, feed_parsing, canonicalization,
transformation, semantic_deduplication, endpoint_identity, geo_attribution,
dns_diagnostics, tcp_diagnostics, tls_diagnostics, proxy_authentication,
health_scoring, client_exports, release_eligibility, publication and
frontend_delivery.

An HTTP 200 response proves neither parse quality nor authenticated proxy
transport. A TCP connection is not a successful proxy login or HTTP tunnel.
TLS handshake success is not validation of WS/gRPC/REALITY and credentials.
Network endpoint identity groups protocol, host and port; it is *not* a
semantic proxy identity and ignores credentials. Consequently, 37,868
repeated endpoint observations in an inventory are not automatically duplicate
proxy configurations. GeoIP allocation is not necessarily physical exit
geography; anycast observations must remain unlocated.

The audit cross-checks source counts and categories; malformed JSON; endpoint
inventory accounting (valid distinct + repeated observations + invalid =
scanned); and network layer counts against sampled diagnostic coverage.
It reports integrity contradictions as failures. Unobserved stages remain
unknown rather than pass or fail. Even current output serialization cannot
establish client import or browser delivery.

## TP, TN, FP, FN and abstention labels

A confusion matrix requires labels established independently of the classifier
being evaluated. Use a JSON array of sample objects. Example:

~~~json
[
  {
    "stage": "feed_parsing",
    "sample_id": "fixture-vmess-001",
    "truth": true,
    "predicted": false,
    "oracle": "independent parser fixture suite release v2"
  },
  {
    "stage": "proxy_authentication",
    "sample_id": "independent-path-002",
    "truth": false,
    "predicted": null,
    "oracle": "separate end-to-end client test with recorded vantage and time"
  }
]
~~~

Positive truth means independently verified. Prediction null means abstention
or insufficient evidence, not false and not true. The sample identity must be
unique within its stage. The oracle description is a provenance claim and
must be verified outside HUNTX; never treat a written string as proof.

TP = true and predicted positive; TN = true and predicted negative; FP =
predicted positive but actually negative; FN = predicted negative but actually
positive. The report computes precision, recall, specificity, false-positive
rate, false-negative rate, negative predictive value, accuracy, coverage and
the abstention count. Undefined denominators give null rather than a
fabricated 0%. Unlabeled stages give null confusion matrices rather than
fabricated success rates.

Representative independent samples should cover valid and invalid protocols,
IPv4 and IPv6, DNS and TLS failures, rotating credentials, duplicate endpoints
with distinct passwords, legitimate empty feeds, censored networks, ASN/anycast
ambiguity, Telegram FloodWait, and every supported client subscription format.
Use independent client import and authenticated traffic tests where relevant.

## Operating the audit

~~~sh
python scripts/audit_pipeline_evidence.py \
  --summary persist/data/logs/run-summary.json \
  --source-health persist/data/logs/source-health.json \
  --endpoint-inventory persist/data/logs/endpoint-inventory.json \
  --network-diagnostics persist/data/logs/network-diagnostics.json \
  --output persist/data/logs/pipeline-evidence-audit.json
~~~

Add --labels independently_verified_labels.json only after collecting and
validating independent ground-truth samples. The default production audit
does not require proxy secrets, raw source URLs or Telegram session keys.

## Limitations / follow-up

Four failing HTTP sources need source-specific recovery and may require
upstream publisher action. Telegram cooldowns must be honored; aggressive
retries are not recovery. The 24 sampled DNS/TCP/TLS observations cannot
stand in for protocol-authenticated verification. Network attribution needs
current verified datasets; unknown is a legitimate outcome. Large persistent
checkpoints require measured and rollback-tested optimization rather than
deleting the only recovery copy.
