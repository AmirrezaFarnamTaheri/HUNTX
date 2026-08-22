# Product Definition: HUNTX

## Purpose

HUNTX aggregates publicly available proxy/VPN configuration material into reproducible, deduplicated artifacts. Its primary product surfaces are generated subscription/configuration files, a verified static catalog, configured Telegram publication destinations, and the approval-gated GatherX Telegram bot.

The repository currently operates one governed Python pipeline rather than a collection of independent services. The production configuration uses 85 Telegram MTProto sources, one aggregate publication route, and 12 configured route formats. Telegram Bot API and Go V2Ray collector source implementations also exist but are not enabled by the current production config.

## Intended users

- operators maintaining the HUNTX aggregation pipeline and its source/publishing policy;
- approved GatherX users receiving selected generated artifacts in direct messages;
- consumers of the generated static output/catalog who understand that third-party proxy endpoints remain untrusted;
- contributors extending source connectors, format handling, validation, release tooling, or operational safeguards.

HUNTX does not claim that an aggregated proxy endpoint is safe, private, reachable, or trustworthy merely because it was discovered or published.

## Implemented product capabilities

1. **Governed source ingestion** — publication-eligible sources are filtered before production ingestion; MTProto production work is windowed, leased, durable, retryable, and processed newest-first.
2. **Durable incremental state** — SQLite/WAL stores source state, observations, normalized records, queue work, publication state, Bot API inbox state, and GatherX delivery/user state; raw source bytes are SHA-256-addressed on disk.
3. **Format and proxy normalization** — registered handlers classify/parse supported text and archive formats; `npvt` and `npvtsub` share protocol-aware proxy URI validation/canonicalization.
4. **Governed artifact construction** — route source membership and publication tier are enforced before building. Proxy routes can additionally produce decoded JSON, base64 subscriptions, and supported sing-box derivatives.
5. **Ledgered publication** — Telegram publication records desired/sending/confirmed/failed/unknown outcomes per destination and does not blindly replay ambiguous sends.
6. **GatherX private delivery** — registration is separate from approval; artifact access and automatic delivery are restricted to approved direct-message identities, with separate numeric-ID administrator controls.
7. **Verified production control plane** — GitHub Actions validates both language planes, optionally restores an immutable S3 state generation, executes the bounded runtime, verifies/package outputs, persists a verified checkpoint when configured, and deploys packageable site data to GitHub Pages.
8. **Operational evidence** — structured run health and investigation metrics distinguish success, recoverable degradation, and fatal outcomes.

## Current product constraints

- The hosted production workflow is scheduled every two hours; the product must not promise sub-hour freshness as an invariant.
- Source discovery/aggregation does not establish endpoint trust.
- Recognition of a proxy protocol is broader than native sing-box conversion; HUNTX does not fabricate unsupported mappings.
- A canonical typed proxy intermediate representation and exhaustive native-client conformance gates are not yet established.
- Optional S3 persistence depends on repository/environment configuration; without it, hosted-run state is ephemeral between runners.

## Product quality goals

These are engineering goals, not unconditional claims:

- **No silent loss at acknowledged persistence boundaries** — queue checkpoints, source cursor updates, Bot API inbox acknowledgement, and publication receipts should be transactional or explicitly recoverable.
- **Fail-closed trust and authorization** — unapproved sources/users must not gain publication/artifact access through alternate entrypoints.
- **Recoverable degradation** — external source/publication failures should preserve valid durable progress and produce structured diagnostics when system invariants remain intact.
- **Deterministic output ownership** — generated files should have explicit route/format ownership and avoid deleting unrelated files.
- **Bounded external work** — downloads, retries, probes, queues, transformations, and run deadlines must have explicit limits.
- **Repository truthfulness** — current documentation should distinguish implemented production behavior, implemented-but-inactive alternatives, historical records, and future opportunities.
