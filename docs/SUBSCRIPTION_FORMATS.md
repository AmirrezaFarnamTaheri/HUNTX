# Subscription feeds, full profiles, and compatibility

## Persistent latest-100 subscriptions (historical, not verified live)

New static GitHub Pages subscriptions are published under
`/HUNTX/subscriptions/latest/` (relative to the Pages project root). They
are rebuilt only on an accepted producer publication. The publisher maintains
an all-time cumulative history separately from the verified release files.

- `<protocol>.txt` contains up to **100 newest-discovered unique URI
  connections** of that protocol. There is **no time-to-live or age cutoff**.
  Old entries are only displaced when more recent entries enter that category.
- `<protocol>_base64.txt` encodes that exact feed as Base64, including its
  terminating newline. Empty categories have empty plaintext and Base64 feeds.
- `all.txt` contains the **full union** of all individual top-100 categories,
  ordered newest first; the total is not capped at 100.
- `all_base64.txt` is the Base64 representation of `all.txt`.
- `index.json` publishes the per-category counts, content hashes, the
  generated timestamp and the aggregate count. Empty categories are listed too.

Every router-supported proxy URI protocol receives a distinct category unless
it is an alias within the same protocol family: e.g. `hy2` →
`hysteria2`, `socks4`/`socks5` → `socks`, `ss` →
`shadowsocks`, and `https` → `http`. There is **no Others category**.
Unknown URI schemes and unvalidated ordinary web links are not accepted as
proxy subscriptions. Binary/opaque configuration formats are intentionally
not forced into invalid URI subscriptions. Supported named families include
Trojan, SOCKS4/5, Hysteria 1/2, AnyTLS, DNS, DNSTT, HTTP(S), and the
SlipNet cleartext share format. These share categories are dynamically
derived from the router registry, and the client UI appends new categories
found in the signed publication index.

SlipNet's `slipnet://` link is a **base64-encoded, pipe-delimited profile**,
not an ordinary host:port proxy URI. Only syntactically validated plain share
profiles from the existing public discovery pipeline are considered. Private
`slipnet-enc://` single-recipient shares and
`slipnet-bundle-enc://` encrypted backups are **excluded**. Do not publish
private SlipNet credentials: base64 encoding does not protect secrets.

The canonical published files are also mirrored at
`/HUNTX/artifacts/dev/latest/`, where every file is included in the
download catalog and aggregate artifact manifest. The generated branch stores
a third copy at `outputs_dev/latest/`.

The historical timestamp is the first-discovery timestamp from the cumulative
manifest (not the most recent successful health probe). These files are marked
`historical_unverified`: old/failed/revoked nodes can remain in the historical
archive, and a retained URI does **not** imply that it works today. The
existing `artifacts/release/` feeds retain their separate authenticated,
current-run acceptance criteria.


HUNTX publishes independent-node feeds and complete client configurations.
These are distinct import contracts.

| Release filename | Content and import mode |
|---|---|
| `all_sources_base64.txt` | Base64-encoded newline-delimited URI list; client subscription |
| `all_sources.txt` | Plain proxy share URI list; import as unencoded subscription |
| `all_sources_singbox_nodes.json` | Outbounds-only Sing-box JSON; independent-node subscription in compatible updaters |
| `all_sources_xray_nodes.json` | Outbounds-only Xray JSON; independent-node subscription in compatible updaters |
| `all_sources_nekobox.json` | Minimal JSON `outbounds` container; independent NekoBox entries in supported versions |
| `all_sources_clash.yaml` | `proxies:` YAML; configure as a **Mihomo/Clash proxy provider**, not a full profile |
| `all_sources_singbox.json` | **Historical full runnable Sing-box profile** with inbound, DNS and routing |
| `all_sources_xray.json` | **Historical full runnable Xray profile** with inbound |
| `all_sources_singbox_profile.json`, `all_sources_xray_profile.json` | Explicit compatibility aliases for the full profiles |

Previously published `all_sources_npvt_singbox.json` and
`all_sources_npvt_xray.json` keep their historical *full profile*
semantics. Do not repurpose an old URL for an incompatible node-only body.
Secondary `npvtsub` feeds use analogous `_sub_` names.

Converters omit unsupported nodes instead of silently rewriting incompatible
transport or security settings. The raw and Base64 URI feeds preserve the
original node list best; separate derived counts describe each format's
actually representable nodes. Valid JSON alone does not prove connectivity.

## Release verification

The output verifier checks syntactic validity and the minimum expected
node-feed/full-profile envelope before copying to `dist`. The test suite
checks publication filenames, format registry classification, bot and web
presentation, and conversion cardinality.

**Still required for production acceptance:** import each published feed into
each supported client/version and verify several individually selectable
nodes, import old profile URLs as runnable full configurations, test live
connectivity, and record client version plus observed results. Unit tests
cannot replace real-device compatibility testing.

## Resolving uncertain Telegram sends

A timeout or lost response after `sendDocument` may mean Telegram accepted
the document. HUNTX records `unknown_outcome` or leaves `sending` after a
crash, and does not automatically resend potentially delivered bytes.
Operators must inspect Telegram's destination and obtain independent
evidence before reconciling:

```sh
python scripts/reconcile_publication.py --db /path/to/state.db \
  --intent-id 123 --destination-id 'destination@config-hash' \
  --outcome confirmed --receipt '{"message_id":42}' \
  --operator oncall --reason 'verified message 42 in destination'
```

For independently verified **non-delivery**, use `--outcome not_delivered`
without `--receipt`, and include the evidence in `--reason`.
The reconciliation audit stores the operator, evidence, transition and time.
A recently active `sending` attempt cannot be reconciled. Elapsed time
alone is not proof of non-delivery.

## Transform work and deadlines

`HUNTX_TRANSFORM_MAX_RECORDS` is the *total run* record budget.
`HUNTX_TRANSFORM_MAX_RECORDS_PER_FILE` bounds one observation. An
observation that yields more than the entire run's budget now raises an
actionable error instead of being silently deferred forever. Increase the
total budget or split the input source safely.

The threaded transformer stops *waiting* after a deadline but Python
threads already executing a parser cannot be forcibly killed by
`ThreadPoolExecutor.cancel()`. Hard process-level limits would require
a separately supervised worker process and remain outside the threaded
runner's present guarantee.

## Distribution installation safety

The verifier copies candidate outputs into a fresh staging directory and
validates those exact bytes before publication. Duplicate filenames from
different output subdirectories, symlinked artifacts, and empty releases
without an explicit nonempty marker fail validation. Only after all products
and helper files are prepared does the installer rename the prior `dist`
out of the way and publish the staged directory; a detected installation
failure restores the previous directory. Publication is not a distributed
transaction or a guarantee against sudden power loss during the two renames.
