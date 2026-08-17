# Subagent C — Formats / Connectors / Publishers Forensics

Scope: `src/huntx/formats/` (22 files), `src/huntx/connectors/` (4 packages), `src/huntx/publishers/` (1 file) · 2,334 + 1,704 + 210 LOC · Written by the lead agent after subagent C context-overflowed; all citations verified file:line.

**Live-verification status:** ✅ = confirmed by reading exact source; 🔍 = derived/inferred; ⚠️ = stale-risk.

---


## 1. Format registry architecture

**Contract** (`formats/base.py:4-22`): `FormatHandler` Protocol — `format_id` property, `parse(raw_data: bytes, source_info) -> List[{unique_hash, data}]`, `build(records) -> bytes`. Runtime-checkable.

**Registry** (`formats/registry.py:8-40`): plain dict; `get_instance()` classmethod is a **compatibility singleton used only by config validation** — runtime owners construct fresh instances so orchestrators can't overwrite each other's handlers (registry.py:16-20, deliberate multi-orchestrator safety). Duplicate registration logs a warning and overwrites (registry.py:26-27).

**Registration** (`formats/register_builtin.py:21-37`): 16 handlers — `conf_lines, npvt, npvtsub, slipnet, ovpn, npv4, ehi, hc, hat, sip, nm, dark, tut, sks, tmt, opaque_bundle`. 11 of them take `raw_store` (blob-backed); `slipnet` takes an optional format_id.

**Routing** (`core/router.py:62-86`, per report A): LRU-cached extension table + content heuristics; 19 proxy URI schemes (`router.py:6-26`).

## 2. Format catalog (all 16 + 3 derivatives + 1 dead)

| Format | File:line | Family | Parse | Build | Prod route | Status |
|---|---|---|---|---|---|---|
| `npvt` | npvt.py:67-137 | URI-line | UTF-8 strict; whole-payload b64 fallback if no `://`/space and >10 chars (npvt.py:99-105); per-line scheme fast-path + mid-line URI regex extraction; **validate_proxy_uri on both raw and remark-stripped** (npvt.py:81-84); dedup by sha256(stripped) | dedup + `add_clean_remark` renumbering (`scheme-N` tags; vmess `ps` JSON rewrite npvt.py:51-60) | ✅ | **LIVE — flagship** |
| `npvtsub` | npvtsub.py:10-86 | URI-line | Same shape as npvt but `errors="ignore"` decode, **no validate_proxy_uri** (npvtsub.py:47-63 — looser than npvt), manual b64 padding (npvtsub.py:29-31) | same remark logic | ✅ | LIVE |
| `conf_lines` | conf_lines.py:7-39 | line | every non-`#` line is a record, hash of raw line | dedup by exact line | ✅ | LIVE |
| `slipnet` | slipnet.py:134-214 | encrypted-link | regex-extract `slipnet-enc://` links → AES-256-GCM decrypt (crypto.py:82-122) → pipe-separated profile parsed against **versioned schemas V1–V28** (slipnet.py:11-111, from "Pantegnos" source-of-truth); boolean field coercion (slipnet.py:113-131) | **NotImplementedError** (slipnet.py:184-185) | ❌ not in route | LIVE-but-unrouted (registered, parse-only) |
| `opaque_bundle` | opaque_bundle.py:35-148 | blob-zip | 1 record per blob (content hash identity) | ZIP of raw blobs with **1 GiB / 100k-entry ceilings** (env-tunable, opaque_bundle.py:18-19,57-58), declared-size pre-filter + real-bytes enforcement (:89-106), O(1) collision naming with documented O(n²) regression fix (:108-129) | ✅ | LIVE |
| `ovpn` | ovpn.py:4-9 | blob-zip | OpaqueBundleHandler subclass, id only | ZIP | ✅ | LIVE |
| `ehi` | ehi.py | blob-zip | id-only subclass | ZIP | ✅ | LIVE |
| `hc` | hc.py | blob-zip | id-only subclass | ZIP | ✅ | LIVE |
| `sip` | sip.py | blob-zip | id-only subclass | ZIP | ✅ | LIVE |
| `dark` | dark.py:6-10 | blob-zip | id-only subclass ("proprietary binary") | ZIP | ✅ | LIVE |
| `hat` | hat.py:14-81 | hybrid | 3-stage: (1) `happ://` links → RSA-PKCS1v15 decrypt w/ 3 versioned keys (crypto.py:50-76); (2) `.tut/.tmt`-style PBKDF2+AES-GCM text decrypt; (3) opaque ZIP fallback. Documents a fixed `LookupError` bug from a bad `"strip"` codec handler (hat.py:56-63) | ZIP (inherited) | ✅ | LIVE |
| `npv4` | npv4.py:13-40 | hybrid | tries `.sks`-style decrypt first, else opaque ZIP | ZIP | ✅ | LIVE |
| `tut` / `sks` / `tmt` | tut.py/sks.py/tmt.py:14-37 | hybrid | PBKDF2(SHA256, 1000 iters) + AES-GCM decrypt (crypto.py:134-168), else opaque ZIP | ZIP | ❌ not in route | LIVE-but-unrouted |
| `nm` | nm.py:13-45 | encrypted | AES-ECB with key `_netsyna_netmod_` (env override `HUNTX_NETMOD_KEY`, crypto.py:240-241); stores ciphertext hex + decrypted text | **NotImplementedError** (nm.py:43-44) | ✅ registered in route but **build raises** — see Defect C2 | LIVE-parse / broken-build |
| `streaming` | streaming.py:10-166 | dead engine | `StreamingChunkParser`: 64 KB-chunk async parser, raw/base64 auto-detect (streaming.py:44-65), incremental UTF-8 decoder, b64 remainder buffering (:95-111) | n/a | ❌ | **DEAD** — only `UnifiedOrchestrator` (unified_orchestrator.py:14,36) + `__init__.py:5` export + tests |
| derivatives `b64sub` / `decoded.json` / `singbox.json` | build.py:246-263,343-383 (report A) | derived from npvt/npvtsub at build time | — | ✅ | LIVE |

**Protocol coverage:** 19 URI schemes validated (router.py:6-26): vmess, vless, trojan, ss, ssr, hysteria2/hy2, hysteria, tuic, wireguard/wg, socks/socks5/socks4, anytls, juicity, warp, dns, dnstt. README "20+ protocols" ≈ accurate; "12 formats" = the prod route, registry has 16.

## 3. Decoding deep-dives (notable)

- **`proxy_uri_validator.py` (189 LOC) — the security crown.** Per-scheme validators: `_validate_ss` handles both `userinfo@endpoint` and base64-body forms, 8-method AEAD whitelist (proxy_uri_validator.py:15-24), empty-plugin rejection (:109-110); `_validate_vmess` requires UUID + int-coercible port + valid host (:130-142); `_validate_standard_uri` enforces vless UUID, **reality requires both pbk and sni** (:161-166), auth-required scheme set (:38-48), hy2 obfs/obfs-password pairing invariant (:169-173). **Host validation rejects loopback/private/link-local/multicast/reserved IPs and localhost/.local** (proxy_uri_validator.py:51-68) — SSRF-grade hygiene for a proxy list. 16 KB URI length cap, whitespace/quote rejection (:178). The `_validate_ss` comment block (:82-88) documents a fixed bug where a raised ValueError would fail an *entire source file* — predicate-purity lesson preserved in code.
- **`common/singbox.py` (603 LOC)** — full URI→sing-box 1.14+ outbound renderer: vmess/vless/trojan/ss/hy2/tuic/anytls parsers, TLS/Reality/uTLS/transport modeling, legacy-protocol deliberate skip policy (singbox.py:1-7). Feeds the `.singbox.json` derivative.
- **`common/crypto.py` (268 LOC)** — 4 crypto stacks: HAPP RSA (env keys `HUNTX_HAPP_CRYPT{,2,3}_PEM` or `persist/keys/happ_*.pem`, crypto.py:18-33), SlipNet AES-GCM with **XOR-assembled key from 8 hardcoded 64-bit constants** (crypto.py:105-111, "from Slipnet decoder.html"), TUT/SKS/TMT PBKDF2+AES-GCM with **hardcoded fallback passwords in source** (crypto.py:127-131), NetMod AES-ECB fixed key (crypto.py:241), plus a full XXTEA-with-custom-delta port "from vpndecrypt-Lol" (crypto.py:174-225) — **XXTEA has no caller in src/** (grep-verified): dead code preserved as a porting artifact.
- **`common/b64.py`** — single-source URL-safe b64 decoder replacing 3 private copies (docstring b64.py:2-6); `validate=True` + padding normalization.
- **`common/normalize_text.py` / `hashing.py`** — NFKC normalization + sha256, both `lru_cache(8192)` (hot-path investment).

## 4. Connectors

**Base contract** (`connectors/base.py:81-99`): `SourceConnector` Protocol — `list_new(state)` returning sync OR async iterator, `get_state()`. Support machinery: `maybe_await` (:9-16), `run_sync` with running-loop detection → worker-thread fallback (:19-41, Python 3.12-safe), `AsyncSyncIterator` dual-protocol wrapper (:44-65), `async_iter` (:68-78).

| Connector | File | Transport | Status |
|---|---|---|---|
| `TelegramConnector` | telegram/connector.py:35-439 | Bot API (getUpdates + getFile), urllib | LIVE (schema-supported) but **0 bot-token sources in prod config** — dormant in production |
| `TelegramUserConnector` | telegram_user/connector.py:70-760 | MTProto via Telethon StringSession | **LIVE — all 85 prod sources** |
| `WindowedTelegramUserConnector` | telegram_user/windowed.py:26-139 | subclass; `fetch_window_page` with continuation cursors for the LIFO queue | LIVE (windowed ingestion path) |
| `V2RayCollectorConnector` | v2ray_collector/connector.py:23-114 | shells out `go run main.go` (300 s timeout, connector.py:65-72), reads `collected_configs.txt` | DORMANT — no prod source configured; needs Go on PATH |

**telegram_user hardening highlights** (issue #44 fixes): per-session **class-level lock tables** for sync (`threading.RLock`, connector.py:72-73,80-84) and async (`asyncio.Lock`, :77-78,86-90) — same ownership key, context-manager acquisition (:92-110); **independent text/document cursors** that advance only after durable commit (`_refresh_committed_offsets` :147-155, pending-set min-1 rule); reconnect ladder `_RECONNECT_DELAYS = (2,2,4,4,8,8,16,16,32,32)` × 10 retries (:38-39,248-262); FloodWait sleep with `_MAX_FLOOD_WAIT_SECONDS` safety bound (:355-362); `download_media_bounded` streaming with explicit stream close (:45-61); resume-from-`min_id` after reconnect (:366-370).

**telegram (Bot API) hardening** (`telegram/hardening.py:10-145`): monkey-patch installer adding **durable ack fencing** — yielded/acknowledged item-key ledgers, failed-update tracking, `recalculate_acknowledgement` computes min(blocking)-1 so unacked/failed updates stay replayable (:43-64); `get_state` returns the *ack-safe* offset, not the scan offset (:123-127); `commit_acknowledgement` persists via inbox consumer ledger (:129-136). Download failures block acknowledgement instead of losing observations (issue #44 contract). `MAX_DOWNLOAD_BYTES = 25 MB` enforced both pre-download (self-reported size) and during read (telegram/connector.py:28-34,137-146).

## 5. Publishers

Single publisher: `publishers/telegram/publisher.py` (210 LOC). **stdlib-only** multipart/form-data encoder (no requests dep, publisher.py:104-141); `secrets.token_hex` boundary; **Content-Disposition filename sanitization against header smuggling** (publisher.py:78-88). Retry: 3 attempts; 429 + in-body `retry_after` honored with `_coerce_retry_after` — type-safe (bool excluded), ceiling `HUNTX_PUBLISH_MAX_RETRY_AFTER_SECONDS` default 60 s (publisher.py:21-75); transport failures (URLError/Timeout/Connection) raise **`UnknownPublicationOutcome`** instead of retrying (publisher.py:199-204) — the ledger's `unknown_outcome` state originates here and blocks auto-resend until manual reconciliation (publish.py:171-179, report A). Token never logged, even prefix (publisher.py:96-102,143).

## 6. Live/dead classification (scope files)

**LIVE:** registry, base, register_builtin, npvt, npvtsub, conf_lines, opaque_bundle (+6 id-subclasses), hat, npv4, tut/sks/tmt (parse; unrouted), nm (parse), slipnet (parse; unrouted), proxy_uri_validator, common/{b64,hashing,normalize_text,crypto,singbox}, connectors/base, telegram_user/*, telegram/* (dormant-in-prod), v2ray_collector (dormant), publishers/telegram.
**DEAD:** formats/streaming.py (tests + UnifiedOrchestrator only); crypto.py `decrypt_xxtea` (zero callers); `FormatRegistry.get_instance` singleton (config-validation compat only).

## 7. Defects & risks (evidence-backed, live-verified where marked)

| # | Sev | Status | Finding |
|---|---|---|---|
| C1 | **HIGH** | ✅ | **Hardcoded decryption passwords in source** — `.tut/.sks/.tmt` fallbacks `b"fubvx788b46v"` / `b"dyv35224nossas!!"` / `b"fubvx788B4mev"` (`crypto.py:128-130`); SlipNet XOR key constants (`crypto.py:105-111`, assembled from 8 literal 64-bit ints in source comment "from Slipnet decoder.html"); NetMod fixed key `_netsyna_netmod_` (`crypto.py:241`). Env overrides exist (`HUNTX_HAPP_CRYPT{,2,3}_PEM`, `HUNTX_TUT_PASSWORD`, `HUNTX_SKS_PASSWORD`, `HUNTX_TMT_PASSWORD`, `HUNTX_NETMOD_KEY`) but **all four fallbacks are committed plaintext**. If these are third-party app secrets scraped from protocol reverse-engineering, committed exposure is an intelligence leak. |
| C2 | **MED** | ✅ | `nm` is in the prod route's 12 formats (`configs/config.prod.yaml:859-871`) but `NmHandler.build` raises `NotImplementedError` (`nm.py:43-44`). Any route building `nm` would crash the build stage. Currently masked because `nm` records are rare/absent — a **latent runtime landmine**. Same for `slipnet` (`slipnet.py:184-185`) though slipnet is unrouted. |
| C3 | **MED** | ✅ | **npvtsub skips URI validation** that npvt applies (`npvtsub.py:47-63` vs `npvt.py:81-84`). The 16 KB cap, whitespace rejection, scheme whitelist, and SSRF-grade IP filtering (`proxy_uri_validator.py:51-68`) are bypassed for any source serving npvtsub. Invalid or private-IP URIs can enter `records`. |
| C4 | **MED** | 🔍 | npvt whole-payload base64 fallback (`npvt.py:99-105`) decodes the ENTIRE file into memory before checking validity — unbounded memory on large non-proxy b64 blobs. `streaming.py`'s chunked detector was built to fix exactly this but is dead (tests only). |
| C5 | **LOW** | 🔍 | `hat`/`npv4`/`tut`/`sks`/`tmt` parse heuristics (`"." in text and len(text) > 50`) are fragile — any dotted text >50 chars attempts a decrypt round. Cheap, but noisy. |
| C6 | **LOW** | 🔍 | SlipNet `unique_hash = hash_string(link)` (`slipnet.py:175`) hashes the ENCRYPTED link while npvt hashes remark-stripped plaintext — identity semantics differ across formats. Undocumented design choice; mixing slipnet and npvt records could produce hash collisions for the same proxy. |
| C7 | **LOW** | ✅ | `decrypt_xxtea` dead port (`crypto.py:174-225`) — zero callers in `src/` (grep-confirmed). Maintenance weight, no production value. |
| C8 | **INFO** | 🔍 | v2ray_collector: `go run` at runtime needs live module download + Go on PATH; fake 100 ms latency in scraper; output file race (remove-then-run, `connector.py:47-52`). Dormant, so low urgency. |

**C1 fix guidance (T8 — secret externalization):**
```python
# crypto.py — replace hardcoded fallback lines 128-131:
# Before:
_TUT_PASSWORD = os.environb.get(b"HUNTX_TUT_PASSWORD", b"fubvx788b46v")
# After (fail-loud if secret not set in production; allow fallback only in dev):
import warnings
_TUT_PASSWORD = os.environb.get(b"HUNTX_TUT_PASSWORD")
if _TUT_PASSWORD is None:
    warnings.warn("HUNTX_TUT_PASSWORD not set; using insecure fallback", RuntimeWarning, stacklevel=0)
    _TUT_PASSWORD = b"fubvx788b46v"  # third-party default; rotate if this is sensitive
# Apply same pattern for _SKS_PASSWORD, _TMT_PASSWORD, _NETMOD_KEY.
# For SlipNet XOR key (crypto.py:105-111): move to env var HUNTX_SLIPNET_XOR_SEED or a key file.
```

**C2 fix guidance:** Raise `NotImplementedError` in `NmHandler.build` is already there. Gate at the route config level: add a validation check in `config/validate.py` that rejects routes including `nm` until `NmHandler.build` is implemented. Alternatively, implement `build` (NetMod AES-ECB encrypt is the reverse of `decrypt_netmod`, `crypto.py:240-265`).



## 8. Hidden/incomplete capabilities

1. **streaming.StreamingChunkParser** — spec-complete chunked parser (conductor next-gen track deliverable), tested, exported, never wired. Revival path: route large-file transform through `parse_stream` to kill C4.
2. **XXTEA port** — suggests a planned/abandoned format (vpndecrypt-Lol lineage) that never shipped.
3. **slipnet profile schemas V1–V28** — a complete reverse-engineered Slipstream protocol spec (slipnet.py:11-111), parse-only; no build/export path.
4. **`detect()` methods** on SlipNetHandler/HatHandler (slipnet.py:149-157, hat.py:27-36) — a content-detection hook **no caller invokes** (router uses extension+heuristics instead). Vestige of an earlier dispatch design.

## 9. Architectural improvements worth absorbing

- **Predicate-purity discipline** in validators (proxy_uri_validator.py:82-88 comment) — never raise from a per-item predicate; documented as a hard-won lesson.
- **Bounded-resource builders** with declared-size pre-filter + real-bytes re-check + explicit drop logging (opaque_bundle.py:81-106,135-146) — pattern to copy into any aggregator.
- **Ack-fencing patch** (telegram/hardening.py) — replay-safe offset advancement as a composable installer; the *pattern* is good, the monkey-patch delivery is the debt (report A D2).
- **Dual sync/async connector contract** with `AsyncSyncIterator` + running-loop-safe `run_sync` (base.py:19-65) — clean bridge worth keeping in any consolidation.
- **`_coerce_retry_after`** (publisher.py:44-75) — untrusted-API-value coercion done right (type narrowing, bool exclusion, ceiling, logging); reusable utility.

## 10. Knowledge preservation (domain knowledge embedded here)

1. **Slipstream/SlipNet protocol**: versioned pipe-separated schemas 1→28 with exact field orders, boolean-field set, AES-GCM payload layout `[version:1][iv:12][ct+tag]`, URL-safe b64, XOR key assembly (slipnet.py + crypto.py:82-122). Rewriting naively loses 8 schema generations.
2. **HAPP (HA Tunnel Plus)**: 3 key generations `crypt/crypt2/crypt3` selected by link prefix, RSA-PKCS1v15, URL-encoded payloads (crypto.py:50-76); `.hat` files are sometimes actually `.tmt`-format text (hat.py:64-77).
3. **TUT/SKS/TMT**: `salt.iv.ciphertext` dot-joined b64, PBKDF2-SHA256 **1000 iterations** matching pycryptodome defaults (crypto.py:147-156 comment), tag = last 16 bytes; `.npv4` often shares `.sks` logic (npv4.py:26).
4. **NetMod**: AES-ECB, key `_netsyna_netmod_`, optional `proto://` prefix preserved around payload (crypto.py:243-265), from "Pantegnos-main (source of truth)".
5. **vmess canonicalization**: remark (`ps`) lives inside the b64 JSON — identity = sorted-key JSON without `ps` (npvt.py:29-43); this exact canonical form is also the DB v10 re-key and the outputs_dev manifest identity — **three subsystems depend on the same canonicalization**; changing it silently re-keys the dedup universe.
6. **ss URI duality**: both `ss://base64(method:pass)@host:port` and `ss://base64(method:pass@host:port)` forms exist; validator handles both (proxy_uri_validator.py:75-111).
7. **Line-level extraction**: real-world subscription posts embed URIs mid-line in prose — regex extraction, not line-splitting, is required (npvt.py:15-18,116-117).
8. **Provenance trail**: Pantegnos(-main), Slipnet decoder.html, vpndecrypt-Lol, smgo — the external projects these decoders were reverse-engineered/ported from; cited in comments, nowhere else.

## 11. Test coverage of scope

`test_formats_coverage.py`, `test_format_registry.py`, `test_format_decoder_hardening.py`, `test_ported_formats.py`, `test_proxy_uri_validator.py`, `test_schema_validators.py`, `test_singbox_export.py`, `test_connector_base_iter.py`, `test_telegram_*` (ownership/cursor/ack per issue #44), `test_download_cap.py`, `test_apk_skipping.py`, `test_v2ray_collector_connector.py` (the 2 env-dependent failures needing Go, report F8), `test_publisher_hardening.py`. Coverage is strong on validators and hardening; weaker on the hybrid decrypt fallbacks (heuristic branches).
