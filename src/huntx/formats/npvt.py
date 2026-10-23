import binascii
import json
import math
import os
import re
import time
from urllib.parse import parse_qs, parse_qsl, quote, unquote, urlsplit
from typing import Any, Dict, List

from .base import FormatHandler
from .common.b64 import b64_decode as _b64_decode_safe
from .common.vmess import canonical_vmess_line, vmess_payload_with_remark
from .common.hashing import hash_string
from .common.normalize_text import normalize_text
from .proxy_uri_validator import validate_proxy_uri
from ..core.router import _AUTH_HTTP_PROXY_RE, _PROXY_SCHEMES
from ..core.remark_geoip import estimate_country

_REPORT_PROXY_SCHEMES = _PROXY_SCHEMES + ('http://', 'https://')
_PROXY_URI_RE = re.compile(
    '(?:' + '|'.join((re.escape(s) for s in _PROXY_SCHEMES)) + ')[^\\s<>"\\\']+',
    re.IGNORECASE,
)


def _is_proxy_line(line: str) -> bool:
    """Return whether a complete line is a supported proxy URI."""
    if any(line.startswith(s) for s in _PROXY_SCHEMES):
        return True
    return line.lower().startswith(('http://', 'https://')) and validate_proxy_uri(line)


def _extract_proxy_uris(text: str) -> List[str]:
    """Extract supported proxy URIs embedded in arbitrary text."""
    matches = _PROXY_URI_RE.findall(text)
    matches.extend(match.group(0) for match in _AUTH_HTTP_PROXY_RE.finditer(text))
    return matches


# Transports worth naming in a remark. "raw"/"" carry no information, and
# naming them would just add noise to every second node.
_REMARK_TRANSPORTS = frozenset({
    'ws', 'websocket', 'grpc', 'http', 'h2', 'xhttp', 'httpupgrade',
    'quic', 'kcp', 'splithttp',
})

# Protocols whose transport is TLS by design. Naming "tls" on them would put the
# same word on every node of that type, which tells a reader nothing.
_TLS_IMPLYING_SCHEMES = frozenset({
    'trojan', 'hysteria', 'hysteria2', 'hy2', 'anytls', 'tuic', 'ssr',
})


def remark_qualifier(uri: str) -> str:
    """Return the transport/security qualifier for one node's remark.

    Deterministic and derived from the URI alone, so the same node always
    produces the same remark. Returns an empty string when the node has no
    distinguishing transport or security, which keeps a plain TCP VLESS node
    reading ``vless-3`` rather than ``vless-tcp-none-3``.
    """
    try:
        from .common.singbox import parse_proxy_uri

        node = parse_proxy_uri(uri)
    except Exception:
        return ''
    if node is None:
        return ''
    parts: list[str] = []
    transport = (node.transport_type or '').strip().lower()
    if transport in _REMARK_TRANSPORTS:
        parts.append('ws' if transport == 'websocket' else transport)
    scheme = (node.type or '').lower()
    if node.tls_reality_enabled:
        parts.append('reality')
    elif node.tls_enabled and scheme not in _TLS_IMPLYING_SCHEMES:
        parts.append('tls')
    return '-'.join(parts)


def strip_proxy_remark(uri: str) -> str:
    """Remove display remarks while preserving proxy semantics."""
    if uri.startswith('vmess://'):
        canonical = canonical_vmess_line(uri)
        return canonical if canonical is not None else uri
    idx = uri.rfind('#')
    if idx > 0:
        return uri[:idx]
    return uri


def canonical_proxy_identity(uri: str) -> str:
    """Semantic key used ONLY for deduplication, never exported as a proxy URI.

    Preserve credentials, transport, TLS, obfuscation, paths, and all unknown
    parameters. Query *key* ordering and display remarks are not connection
    identity. Repeated values for a key retain their original order because
    their order may affect a client; we do not treat IP/port alone as identity.
    """
    bare = strip_proxy_remark(uri.strip())
    try:
        from .common.proxy_identity import client_identity

        typed = client_identity(bare)
        if typed is not None:
            return typed
        parsed = urlsplit(bare)
        scheme = parsed.scheme.lower()
        if scheme == 'vmess':
            # VMess is a base64 JSON payload, canonicalized by strip_proxy_remark.
            return 'vmess|' + bare.partition('://')[2]
        if scheme == 'ss':
            # Normalize standard and SIP002 encoded Shadowsocks credentials,
            # which otherwise survive URI-text deduplication as two copies.
            from .common.singbox import parse_proxy_uri
            node = parse_proxy_uri(bare)
            if node and node.type == 'shadowsocks' and node.server and node.port:
                # Other SIP002 query options may alter the connection but
                # are not modeled by this parser; keep them in the identity
                # rather than silently merging different unknown options.
                unknown: dict[str, list[str]] = {}
                for key, value in parse_qsl(parsed.query, keep_blank_values=True):
                    if key not in {'plugin', 'plugin-opts', 'plugin_opts'}:
                        unknown.setdefault(key, []).append(value)
                return json.dumps([
                    'ss', node.server.lower(), node.port, node.method.lower(),
                    node.password, node.plugin, node.plugin_opts,
                    sorted(unknown.items()),
                ], ensure_ascii=False, separators=(',', ':'))
        if not parsed.hostname:
            return bare
        port = parsed.port  # May reject multiport URLs; keep those opaque.
        aliases = {'hy2': 'hysteria2'}
        scheme = aliases.get(scheme, scheme)
        params: dict[str, list[str]] = {}
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            normalized_key = key.strip()
            if normalized_key in {'type', 'network', 'security'}:
                value = value.lower()
            if normalized_key in {'sni', 'peer'}:
                value = value.lower()
            params.setdefault(normalized_key, []).append(value)
        query = [(key, values) for key, values in sorted(params.items())]
        return json.dumps([
            scheme, parsed.hostname.lower(), port,
            unquote(parsed.username or ''), unquote(parsed.password or ''),
            parsed.path, query
        ], ensure_ascii=False, separators=(',', ':'))
    except (ValueError, TypeError, UnicodeError, OverflowError):
        # Malformed/opaque formats must not be folded into a false match.
        return bare


def _country_to_flag(code: str) -> str:
    """Convert ISO 2-letter country code to emoji flag."""
    code = code.upper().strip()
    if len(code) != 2 or not code.isascii() or not code.isalpha() or code == "ZZ":
        return "🌐"
    return chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)


def _detect_operator(uri: str) -> str:
    """Infer operator or CDN name from URI string."""
    low = uri.lower()
    if uri.startswith('vmess://'):
        try:
            b64 = uri[8:]
            decoded_text = _b64_decode_safe(b64).lower()
            low = f"{low} {decoded_text}"
        except Exception:
            pass
    if any(k in low for k in ("mci", "mcci", "hamrah")):
        return "MCI"
    if any(k in low for k in ("mtn", "irancell")):
        return "MTN"
    if any(k in low for k in ("rtl", "rightel")):
        return "RTL"
    if any(k in low for k in ("cloudflare", "cf-", "workers.dev", "pages.dev")):
        return "CF"
    if any(k in low for k in ("hetzner", "your-server.de")):
        return "Hetzner"
    if any(k in low for k in ("digitalocean", "do-")):
        return "DO"
    if "ovh" in low:
        return "OVH"
    if "arvan" in low:
        return "Arvan"
    return ""


def format_enriched_remark(uri: str, counter: dict, metadata: dict | None = None) -> str:
    """Format an information-dense display remark with geo, protocol, and stats.

    Not wired to the published feed. Every production call site of
    ``add_clean_remark`` passes no metadata, so the published artifacts carry the
    clean ``{scheme}-{n}`` tag. The dashboard displays that exact string, so a
    node reads the same in a client as it does on the site. Adopting this form
    for the feed would change what subscribers see and break that parity; it is
    available for a surface that wants geo and grade in the remark itself.
    """
    scheme = uri.split('://')[0].lower() if '://' in uri else 'proxy'
    counter[scheme] = counter.get(scheme, 0) + 1
    idx = counter[scheme]

    if not metadata:
        tag = f'{scheme}-{idx}'
    else:
        raw_country = metadata.get('country')
        country = raw_country.strip().upper() if isinstance(raw_country, str) else 'ZZ'
        if len(country) != 2 or not country.isascii() or not country.isalpha():
            country = 'ZZ'
        flag = _country_to_flag(country)
        # An upstream remark/secret is not operator evidence. Display only
        # an explicitly verified operator label, never one guessed from URI text.
        operator = metadata.get('operator')
        op = operator.strip()[:24] if (
            isinstance(operator, str) and metadata.get('operator_verified') is True
            and operator.strip().isascii()
            and operator.strip().replace('-', '').isalnum()
        ) else ''
        operator_tag = f"OP:{op}" if op else ""
        # Protocol tag carries the transport and security actually in use so
        # a user picking a node from a long list can tell a plain TCP VLESS
        # from a REALITY-over-gRPC one at a glance.
        proto_tag = scheme.upper()
        transport = metadata.get('transport') or metadata.get('network') or ''
        security = metadata.get('security') or ''
        for detail in (transport, security):
            if isinstance(detail, str) and detail.strip().lower() not in ('', 'none', 'auto', 'unknown'):
                proto_tag += '-' + detail.strip().upper()

        # The flag alone communicates a country. Never repeat DE, NL or ZZ.
        parts = [f"{flag} {proto_tag}"]
        if operator_tag:
            parts.append(operator_tag)

        latency = metadata.get('latency_ms')
        if (
            isinstance(latency, (int, float))
            and not isinstance(latency, bool)
            and latency >= 0
            and math.isfinite(latency)
        ):
            parts.append(f"⚡{latency}ms")
        # A measured probe result outranks a caller-declared grade: an
        # unreachable node advertises its failure instead of a score.
        grade = metadata.get('health_grade')
        probe_failed = metadata.get('probe_ok') is False
        authenticated = (
            metadata.get('probe_kind') == 'protocol_authenticated'
            and metadata.get('probe_ok') is True
            and isinstance(metadata.get('probe_age_seconds'), (int, float))
            and not isinstance(metadata.get('probe_age_seconds'), bool)
            and math.isfinite(metadata['probe_age_seconds'])
            and 0 <= metadata['probe_age_seconds'] <= 3600
        )
        if probe_failed:
            parts.append("⭐F")
        elif authenticated and isinstance(grade, str) and grade.strip() in {
            'A+', 'A', 'B', 'C', 'D', 'F'
        }:
            parts.append(f"⭐{grade.strip()}")
        parts.append(f"#{idx:03d}")
        tag = " | ".join(parts)

    return tag


# ISO hints are deliberately separate from independently sourced IP evidence.
_HINT_COUNTRIES = frozenset(("AD AE AF AG AI AL AM AO AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BM BN BO BR BS BT BW BY BZ CA CD CF CG CH CI CK CL CM CN CO CR CU CV CY CZ DE DJ DK DM DO DZ EC EE EG ER ES ET FI FJ FM FO FR GA GB GD GE GF GH GI GM GN GQ GR GT GU GW GY HK HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW").split())
_COUNTRY_NAMES = {"GERMANY": "DE", "FRANCE": "FR", "NETHERLANDS": "NL", "UNITED STATES": "US", "UNITED KINGDOM": "GB", "CANADA": "CA", "SWEDEN": "SE", "SINGAPORE": "SG", "JAPAN": "JP", "IRAN": "IR", "RUSSIA": "RU", "AUSTRALIA": "AU", "EGYPT": "EG"}


def _remark_country_hint(uri: str) -> str | None:
    """Recognize explicitly labeled source country, never infer it from secrets."""
    fragment = uri.split('#', 1)[1] if '#' in uri else ''
    if uri.lower().startswith('vmess://'):
        try:
            decoded = json.loads(_b64_decode_safe(uri.partition('#')[0][8:]))
            fragment = decoded.get('ps', '') if isinstance(decoded, dict) else ''
        except (ValueError, UnicodeError, binascii.Error, TypeError):
            fragment = ''
    if not isinstance(fragment, str) or not fragment or len(fragment) > 256:
        return None
    readable = unquote(fragment).upper()
    for match in re.finditer(r'[\U0001F1E6-\U0001F1FF]{2}', readable):
        code = ''.join(chr(ord(symbol) - 127397) for symbol in match.group())
        if code in _HINT_COUNTRIES:
            return code
    for match in re.finditer(r'(?<![A-Z])([A-Z]{2})(?![A-Z])', readable):
        if match.group(1) in _HINT_COUNTRIES:
            return match.group(1)
    for name, code in _COUNTRY_NAMES.items():
        if re.search(r'(?<![A-Z])' + re.escape(name) + r'(?![A-Z])', readable):
            return code
    return None


def _tls_verification_bypassed(uri: str) -> bool:
    """Detect explicit certificate-validation bypasses without exposing secrets."""
    insecure_keys = frozenset({
        'allowinsecure', 'insecure', 'skipcertverify',
        'skip-cert-verify', 'allow_insecure', 'tlsinsecure',
    })
    true_values = frozenset({'true', '1', 'yes', 'on'})
    try:
        if uri.lower().startswith('vmess://'):
            encoded = uri.partition('#')[0][8:]
            fields = json.loads(_b64_decode_safe(encoded))
            if isinstance(fields, dict):
                return any(
                    str(value).strip().lower() in true_values
                    for key, value in fields.items()
                    if str(key).lower() in insecure_keys
                )
            return False
        params = parse_qs(urlsplit(uri).query, keep_blank_values=True)
        return any(
            str(value).strip().lower() in true_values
            for key, values in params.items()
            if key.lower() in insecure_keys for value in values
        )
    except (ValueError, UnicodeError, binascii.Error, TypeError):
        return False


def _fresh_number(fields: dict, name: str, *, checked_at: str, expires_at: str) -> float | None:
    """Accept only finite, nonnegative, unexpired, explicitly dated readings."""
    value = fields.get(name)
    observed = fields.get(checked_at)
    expiry = fields.get(expires_at)
    if not all(
        isinstance(item, (int, float)) and not isinstance(item, bool)
        and math.isfinite(item)
        for item in (value, observed, expiry)
    ):
        return None
    # Explicit guards let static type checking enforce the same runtime
    # freshness boundary as the feed validator.
    if not isinstance(value, (int, float)):
        return None
    if not isinstance(observed, (int, float)):
        return None
    if not isinstance(expiry, (int, float)):
        return None
    if value < 0 or observed > time.time() or expiry <= time.time():
        return None
    return float(value)


def _safe_endpoint_label(uri: str) -> str:
    """Use connection host and port, never userinfo, URI fragments or secrets."""
    try:
        if uri.lower().startswith('vmess://'):
            fields = json.loads(_b64_decode_safe(strip_proxy_remark(uri)[8:]))
            if not isinstance(fields, dict):
                return ''
            address = str(fields.get('add') or '').strip()
            port = int(fields.get('port') or 0)
        else:
            from .common.singbox import parse_proxy_uri
            node = parse_proxy_uri(uri)
            if node is not None:
                address, port = node.server, node.port
            else:
                parsed = urlsplit(uri)
                address, port = parsed.hostname or '', parsed.port or 0
        # A username/password never enters the label. Keep a readable domain
        # or IP address rather than an opaque digest.
        address = re.sub(r'[^a-zA-Z0-9.:_-]', '', str(address)).strip('.')
        if not address or not 0 < int(port) <= 65535:
            return ''
        return f'{address[:44]}:{port}'
    except (ValueError, TypeError, UnicodeError, OverflowError, binascii.Error):
        return ''


def format_evidence_remark(uri: str, metadata: dict | None = None) -> str:
    """Display useful observable facts without invented geo or fake throughput.

    Country is represented by a single flag, or a globe for unknown country;
    source-hint provenance stays in metadata. Internal canonical
    identity never appears in user-facing names. TCP/DNS are not authenticated
    proxy evidence, and configured bandwidth is not a speed test.
    """
    fields = metadata if isinstance(metadata, dict) else {}
    endpoint = fields.get('endpoint')
    endpoint = endpoint if isinstance(endpoint, dict) else {}
    intel = endpoint.get('intelligence')
    intel = intel if isinstance(intel, dict) else {}
    geo = endpoint.get('geo')
    geo = geo if isinstance(geo, dict) else {}
    expiry = intel.get('expires_at')
    intel_fresh = (
        intel.get('status') == 'matched'
        and isinstance(expiry, (int, float)) and not isinstance(expiry, bool)
        and math.isfinite(expiry) and expiry > time.time()
    )
    country = geo.get('country_code')
    trustworthy_location = (
        intel_fresh and geo.get('status') == 'prefix_dataset_estimate'
        and isinstance(country, str) and country in _HINT_COUNTRIES
    )
    estimated = fields.get('country_estimate')
    if not trustworthy_location and isinstance(estimated, str) and estimated in _HINT_COUNTRIES:
        country = estimated
        trustworthy_location = True
    location = '🌐'
    if trustworthy_location and isinstance(country, str):
        location = _country_to_flag(country)
    elif (fields.get('country_hint_source') == 'source_remark'
          and isinstance(fields.get('country_hint'), str)
          and fields['country_hint'] in _HINT_COUNTRIES):
        hint = fields['country_hint']
        location = _country_to_flag(hint)

    scheme = uri.split('://', 1)[0].upper() if '://' in uri else 'PROXY'
    protocol = re.sub(r'[^A-Z0-9+_-]', '', scheme)[:18] or 'PROXY'
    qualifier = remark_qualifier(uri).upper()
    label = protocol + (('-' + qualifier[:24]) if qualifier else '')
    target = _safe_endpoint_label(uri)
    details: list[str] = []

    if _tls_verification_bypassed(uri):
        details.append('UNSAFE-TLS')
    asn = endpoint.get('asn')
    if intel_fresh and type(asn) is int and 0 < asn <= 4294967295:
        details.append(f'AS{asn}')
        cdn = endpoint.get('cdn_provider')
        if isinstance(cdn, str):
            cleaned = re.sub(r'[^a-zA-Z0-9 -]', '', cdn).strip()[:15]
            if cleaned:
                details.append('CDN:' + cleaned.replace(' ', '-'))

    # DNS observations need their own freshness and provenance, independent
    # of a TCP connect or a prefix dataset attribution.
    dns = fields.get('dns_status')
    dns_obs = fields.get('dns_checked_at')
    dns_exp = fields.get('dns_expires_at')
    if (
        dns in {'resolved', 'failed'}
        and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                and math.isfinite(v) for v in (dns_obs, dns_exp))
        and isinstance(dns_obs, (float, int))
        and isinstance(dns_exp, (float, int))
        and dns_obs <= time.time() < dns_exp
    ):
        details.append('DNS:OK' if dns == 'resolved' else 'DNS:FAIL')

    latency = _fresh_number(fields, 'latency_ms',
                            checked_at='probe_checked_at', expires_at='probe_expires_at')
    if latency is not None and latency <= 60000:
        if fields.get('probe_kind') == 'tcp_connect':
            details.append(f'TCP:{round(latency)}ms')
        elif (fields.get('probe_kind') == 'protocol_authenticated'
              and fields.get('probe_authenticated') is True):
            details.append(f'AUTH:{round(latency)}ms')

    # Speeds are shown ONLY after an actual authenticated end-to-end speed
    # measurement, never from a Hysteria2 uplink/downlink CONFIG setting.
    if (fields.get('speed_kind') == 'authenticated_throughput'
            and fields.get('speed_authenticated') is True):
        for key, display in [('download_mbps', 'DL'), ('upload_mbps', 'UL')]:
            value = _fresh_number(fields, key, checked_at='speed_checked_at',
                                  expires_at='speed_expires_at')
            if value is not None and value <= 100000:
                details.append(f'{display}:{value:.1f}Mb/s')

    # Join the icon and protocol as one visual unit: 🌐 TROJAN-WS.
    components = [f'{location} {label}']
    if target:
        components.append(target)
    # No fabricated ping/speed. An unmeasured proxy still has protocol and
    # destination, which are useful discriminators in a client dropdown.
    components.extend(details)
    index = fields.get('_remark_ordinal')
    display_name = components[0]
    for detail in components[1:]:
        if len(display_name) + len(detail) + 3 > 110:
            continue
        display_name += ' | ' + detail
    if type(index) is int and index > 1:
        # A numeric collision marker is last and reserved; unlike a cut-off
        # SHA digest it is not presented as diagnostic information.
        suffix = f' | No.{index}'
        display_name = display_name[:110 - len(suffix)].rstrip(' |') + suffix
    return display_name[:110]


def add_clean_remark(uri: str, counter: dict, metadata: dict | None = None) -> str:
    """Attach a deterministic display remark to a proxy URI.

    Legacy ordinal tags remain the default for client compatibility. Enabling
    HUNTX_REMARK_STYLE=stable replaces the ordinal with a 48-bit canonical URI
    digest, avoiding name churn when sources reorder. Neither mode invents
    country, speed, or health status.
    """
    evidence_style = os.getenv("HUNTX_REMARK_STYLE", "legacy").lower() == "evidence"
    if evidence_style:
        tag = format_evidence_remark(uri, metadata)
    elif metadata:
        tag = format_enriched_remark(uri, counter, metadata)
    else:
        scheme = uri.split('://')[0].lower() if '://' in uri else 'proxy'
        qualifier = remark_qualifier(uri)
        # Preserve established client tags by default. Operators may opt into
        # deterministic identities (HUNTX_REMARK_STYLE=stable) when migrating
        # subscribers; never attach unverified geo/latency marketing labels.
        if os.getenv("HUNTX_REMARK_STYLE", "legacy").lower() == "stable":
            identity = hash_string(strip_proxy_remark(uri))[:12]
        else:
            counter[scheme] = counter.get(scheme, 0) + 1
            identity = str(counter[scheme])
        tag = f'{scheme}-{qualifier}-{identity}' if qualifier else f'{scheme}-{identity}'

    if uri.startswith('vmess://'):
        remarked = vmess_payload_with_remark(uri, tag)
        return remarked if remarked is not None else uri
    idx = uri.rfind('#')
    base = uri[:idx] if idx > 0 else uri
    return f'{base}#{quote(tag, safe="-._~") if evidence_style else tag}'


class NpvtHandler(FormatHandler):
    """Parse validated proxy URI records and build deterministic subscriptions."""

    @property
    def format_id(self) -> str:
        """Return the format identifier."""
        return 'npvt'

    def _append_uri(
        self,
        records: List[Dict[str, Any]],
        seen_hashes: set[str],
        candidate: str,
    ) -> None:
        """Validate, deduplicate, and append one proxy URI record."""
        uri = candidate.strip()
        if not validate_proxy_uri(uri):
            return
        stripped = strip_proxy_remark(uri)
        if not validate_proxy_uri(stripped):
            return
        digest = hash_string(canonical_proxy_identity(stripped))
        if digest in seen_hashes:
            return
        seen_hashes.add(digest)
        payload = {'line': stripped}
        if os.getenv("HUNTX_REMARK_STYLE", "legacy").lower() == "evidence":
            hint = _remark_country_hint(uri)
            if hint:
                payload['country_hint'] = hint
                payload['country_hint_source'] = 'source_remark'
        records.append({'unique_hash': digest, 'data': payload})

    def parse(
        self,
        raw_data: bytes,
        source_info: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Parse proxy text into validated deduplicated records."""
        try:
            text = raw_data.decode('utf-8')
        except UnicodeDecodeError:
            return []
        clean_text = text.strip()
        if '://' not in clean_text and ' ' not in clean_text and len(clean_text) > 10:
            try:
                decoded = _b64_decode_safe(clean_text)
                if any(s in decoded for s in _PROXY_SCHEMES) or _AUTH_HTTP_PROXY_RE.search(decoded):
                    text = decoded
            except (binascii.Error, UnicodeDecodeError, ValueError):
                pass
        records: List[Dict[str, Any]] = []
        seen_hashes: set[str] = set()
        for line in text.splitlines():
            clean = normalize_text(line)
            if not clean:
                continue
            if _is_proxy_line(clean):
                self._append_uri(records, seen_hashes, clean)
                continue
            for uri in _extract_proxy_uris(clean):
                self._append_uri(records, seen_hashes, uri)
        return records

    def build(self, records: List[Dict[str, Any]]) -> bytes:
        """Build a deterministic newline-delimited proxy subscription."""
        if os.getenv("HUNTX_REQUIRE_PROXY_HEALTH", "0") == "1":
            from ..core.proxy_health import verified_records

            records = verified_records(records)
        lines = []
        seen = set()
        remark_counter: dict = {}
        rich = os.getenv("HUNTX_REMARK_STYLE", "legacy").lower() == "evidence"
        observations: dict[str, dict] = {}
        if rich and os.getenv("HUNTX_REMARK_TCP_PROBE", "").strip() == "1":
            from ..core.remark_probe import probe_remark_evidence
            candidates = [
                item.get("data", {}).get("line") if isinstance(item.get("data"), dict)
                else item.get("line")
                for item in records if isinstance(item, dict)
            ]
            observations = probe_remark_evidence(
                [link for link in candidates if isinstance(link, str)]
            )
        prefix_intel = None
        if rich:
            from ..core.endpoint_intelligence import PrefixIntelligence
            intel_path = os.getenv("HUNTX_NETWORK_INTELLIGENCE_PATH", "").strip()
            if intel_path:
                try:
                    prefix_intel = PrefixIntelligence.from_file(intel_path)
                except (OSError, ValueError):
                    prefix_intel = None
        for record in records:
            line = None
            evidence_metadata = None
            if isinstance(record, dict):
                if 'data' in record and isinstance(record['data'], dict):
                    line = record['data'].get('line')
                    if os.getenv("HUNTX_REMARK_STYLE", "legacy").lower() == "evidence":
                        evidence_metadata = record['data']
                elif 'line' in record:
                    line = record['line']
            if not isinstance(line, str) or not validate_proxy_uri(line):
                continue
            stripped = strip_proxy_remark(line)
            identity = canonical_proxy_identity(stripped)
            if identity not in seen:
                seen.add(identity)
                if rich:
                    observed = observations.get(line)
                    if observed and (not isinstance(evidence_metadata, dict)
                                     or evidence_metadata.get('probe_kind') != 'protocol_authenticated'):
                        evidence_metadata = {**(evidence_metadata or {}), **observed}
                    # Older persisted records predate the endpoint metadata
                    # contract. Enrich at read time without mutating the
                    # canonical observation or changing the raw link.
                    from ..core.endpoint_intelligence import describe_proxy_endpoint

                    stored = evidence_metadata if isinstance(evidence_metadata, dict) else {}
                    endpoint = stored.get("endpoint")
                    intel = endpoint.get("intelligence") if isinstance(endpoint, dict) else None
                    expiry = intel.get("expires_at") if isinstance(intel, dict) else None
                    expires_at = float(expiry) if isinstance(expiry, (float, int)) and expiry is not None and not isinstance(expiry, bool) else float('inf')
                    stale = math.isfinite(expires_at) and expires_at <= time.time()
                    if not isinstance(endpoint, dict) or stale or prefix_intel is not None:
                        discovered = describe_proxy_endpoint(stripped, intelligence=prefix_intel)
                        if discovered is not None:
                            evidence_metadata = {**stored, "endpoint": discovered}
                if rich:
                    stored = evidence_metadata if isinstance(evidence_metadata, dict) else {}
                    endpoint = stored.get("endpoint")
                    host = endpoint.get("ip") if isinstance(endpoint, dict) else None
                    if not host:
                        host = stored.get("geoip_address")
                    if not host and isinstance(endpoint, dict):
                        host = endpoint.get("host")
                    country_estimate = estimate_country(host) if isinstance(host, str) else None
                    if country_estimate:
                        evidence_metadata = {**stored, "country_estimate": country_estimate}
                if rich:
                    # A collision is two distinct credential/config identities
                    # sharing one human-readable endpoint description. Disclose
                    # no UUID/hash: only add a small ordinal for display.
                    stored = evidence_metadata if isinstance(evidence_metadata, dict) else {}
                    preview = format_evidence_remark(stripped, stored)
                    ordinal = remark_counter.get(preview, 0) + 1
                    remark_counter[preview] = ordinal
                    evidence_metadata = {**stored, '_remark_ordinal': ordinal}
                lines.append(add_clean_remark(stripped, remark_counter, evidence_metadata))
        return '\n'.join(lines).encode('utf-8')
