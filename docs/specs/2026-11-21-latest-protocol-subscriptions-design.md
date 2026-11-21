# Persistent latest-100 subscriptions design

**Approved:** 2026-11-21
**Repository:** HUNTX

## Scope

Create a static subscription for each recognized, syntactically valid proxy URI protocol family. Keep the most recent 100 distinct connections for each family, without a time-based age cutoff. Publish a separate uncapped master aggregate comprising the exact union of those per-family feeds. There is no generic `others` bucket; newly supported URI schemes have separate named feeds.

## Data flow

1. The existing snapshot assembler loads the previous and current historical manifests and compactly deduplicates semantic proxy identities, retaining discovery timestamps.
2. A focused latest-subscriptions component validates supported URI spellings, groups by canonical protocol family, deduplicates connections, sorts by first-discovery timestamp descending with stable lexical tie breaks and selects up to 100 from each category.
3. The component emits `<category>.txt`, `<category>_base64.txt`, `all.txt`, `all_base64.txt`, and `index.json`. Empty categories get empty files. Base64 variants encode exactly the plain-feed bytes.
4. The assembler stores the generated feeds in `outputs_dev/latest/`, publishes `docs/subscriptions/latest/`, and mirrors downloads under `docs/artifacts/dev/latest/`.
5. The artifact catalog and root aggregate manifest include every mirrored file with checksums. The Pages validator verifies both generated copies, Base64 parity, URI classification, per-category limits, and the master union.

## Invariants

- No timer-based expiry, no global aggregate cap, and no mixing of unrelated protocol families.
- Normalized aliases: `hy2` → `hysteria2`, `ss` → `shadowsocks`, `ssr` → `shadowsocksr`, SOCKS versions → `socks`, HTTP(S) → `http`, WireGuard aliases → `wireguard`, and Naive variants → `naive`.
- Ordinary URLs, unsupported schemes, and opaque/non-URI payloads do not enter URI subscriptions.
- The immutable historical discovery timestamp is not a working-proxy health claim. Historical latest subscriptions remain clearly separate from the authenticated release feeds.
- Publication is deterministic, cataloged, and reproducible; a failed publisher cannot claim a fresh release.

## Verification

Test category boundaries, invalid URI rejection, alias deduplication, credentials not collapsed, exact top-100 selection without TTL, aggregate equality and ordering, Base64 parity, deterministic replay, and Pages mirror/catalog tamper detection. Run the focused Python tests and existing repository CI; a PR may be merged only after CI confirms the required checks.
