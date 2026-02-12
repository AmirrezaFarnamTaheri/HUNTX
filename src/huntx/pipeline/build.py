import base64
import json
import logging
import time
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, parse_qs, unquote
from ..state.repo import StateRepo
from ..store.artifact_store import ArtifactStore
from ..formats.registry import FormatRegistry

logger = logging.getLogger(__name__)

# An empty ZIP file (no entries) is exactly 22 bytes.
# Artifacts at or below this size are useless and should be skipped.
_EMPTY_ZIP_THRESHOLD = 22

# All proxy URI schemes
_PROXY_SCHEMES = (
    "vmess://", "vless://", "trojan://",
    "ss://", "ssr://",
    "hysteria2://", "hy2://", "hysteria://",
    "tuic://",
    "wireguard://", "wg://",
    "socks://", "socks5://", "socks4://",
    "anytls://",
    "juicity://",
    "warp://",
    "dns://", "dnstt://",
)


class BuildPipeline:
    def __init__(self, state_repo: StateRepo, artifact_store: ArtifactStore, registry: FormatRegistry):
        self.state_repo = state_repo
        self.artifact_store = artifact_store
        self.registry = registry

    # ------------------------------------------------------------------
    # Protocol decoders
    # ------------------------------------------------------------------

    @staticmethod
    def _b64_decode(data: str) -> str:
        """Base64 decode with auto-padding, supports URL-safe variant."""
        data = data.replace("-", "+").replace("_", "/")
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.b64decode(data).decode("utf-8", errors="ignore")

    @staticmethod
    def _parse_standard_uri(line: str, protocol: str) -> Dict[str, Any]:
        """Parse a standard proxy URI: scheme://userinfo@host:port?params#tag"""
        try:
            parsed = urlparse(line)
            params = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}
            result: Dict[str, Any] = {"protocol": protocol}
            if parsed.username:
                result["user"] = unquote(parsed.username)
            if parsed.password:
                result["password"] = unquote(parsed.password)
            if parsed.hostname:
                result["address"] = parsed.hostname
            if parsed.port:
                result["port"] = parsed.port
            if parsed.fragment:
                result["tag"] = unquote(parsed.fragment)
            if params:
                result["params"] = params
            return result
        except Exception:
            return {"protocol": protocol}

    @staticmethod
    def _decode_vmess(line: str) -> Dict[str, Any]:
        try:
            b64 = line[8:]
            raw = BuildPipeline._b64_decode(b64)
            obj = json.loads(raw)
            return {"protocol": "vmess", "decoded": obj, "raw": line}
        except Exception:
            return {"protocol": "vmess", "raw": line, "error": "decode_failed"}

    @staticmethod
    def _decode_ss(line: str) -> Dict[str, Any]:
        """Decode ss:// — SIP002 or legacy format."""
        try:
            rest = line[5:]  # strip "ss://"
            tag = ""
            if "#" in rest:
                rest, tag = rest.rsplit("#", 1)
                tag = unquote(tag)

            if "@" in rest:
                userinfo, hostport = rest.rsplit("@", 1)
                # SIP002: userinfo is base64(method:password) or plain method:password
                try:
                    decoded_ui = BuildPipeline._b64_decode(userinfo)
                    if ":" in decoded_ui:
                        method, password = decoded_ui.split(":", 1)
                    else:
                        method, password = decoded_ui, ""
                except Exception:
                    parts = unquote(userinfo).split(":", 1)
                    method = parts[0]
                    password = parts[1] if len(parts) > 1 else ""
                host_parts = hostport.split("?")[0]
                if ":" in host_parts:
                    host, port_s = host_parts.rsplit(":", 1)
                    port = int(port_s)
                else:
                    host, port = host_parts, 0
                return {"protocol": "shadowsocks", "method": method, "password": password,
                        "address": host, "port": port, "tag": tag, "raw": line}
            else:
                # Legacy: entire thing is base64
                decoded = BuildPipeline._b64_decode(rest.split("?")[0])
                if "@" in decoded:
                    mp, hp = decoded.rsplit("@", 1)
                    method, password = mp.split(":", 1) if ":" in mp else (mp, "")
                    host, port_s = hp.rsplit(":", 1) if ":" in hp else (hp, "0")
                    return {"protocol": "shadowsocks", "method": method, "password": password,
                            "address": host, "port": int(port_s), "tag": tag, "raw": line}
                return {"protocol": "shadowsocks", "raw": line, "decoded_text": decoded}
        except Exception:
            return {"protocol": "shadowsocks", "raw": line, "error": "decode_failed"}

    @staticmethod
    def _decode_ssr(line: str) -> Dict[str, Any]:
        """Decode ssr:// — base64 of host:port:protocol:method:obfs:base64(password)/?params"""
        try:
            decoded = BuildPipeline._b64_decode(line[6:])
            main_part, _, param_part = decoded.partition("/?")
            parts = main_part.split(":")
            if len(parts) >= 6:
                server = ":".join(parts[:-5])  # handle IPv6
                port, protocol, method, obfs, b64pass = parts[-5], parts[-4], parts[-3], parts[-2], parts[-1]
                password = BuildPipeline._b64_decode(b64pass)
                result: Dict[str, Any] = {
                    "protocol": "shadowsocksr", "server": server, "port": int(port),
                    "ssr_protocol": protocol, "method": method, "obfs": obfs, "password": password,
                }
                if param_part:
                    for kv in param_part.split("&"):
                        if "=" in kv:
                            k, v = kv.split("=", 1)
                            try:
                                result[k] = BuildPipeline._b64_decode(v)
                            except Exception:
                                result[k] = v
                result["raw"] = line
                return result
            return {"protocol": "shadowsocksr", "raw": line, "decoded_text": decoded}
        except Exception:
            return {"protocol": "shadowsocksr", "raw": line, "error": "decode_failed"}

    def _decode_single_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Decode a single proxy URI line into structured JSON."""
        if line.startswith("vmess://"):
            return self._decode_vmess(line)
        if line.startswith("ss://") and not line.startswith("ssr://"):
            return self._decode_ss(line)
        if line.startswith("ssr://"):
            return self._decode_ssr(line)

        # Standard URI protocols — parse with urlparse
        _STANDARD_PROTOS = {
            "vless://": "vless", "trojan://": "trojan",
            "hysteria2://": "hysteria2", "hy2://": "hysteria2", "hysteria://": "hysteria",
            "tuic://": "tuic",
            "wireguard://": "wireguard", "wg://": "wireguard",
            "socks://": "socks", "socks5://": "socks5", "socks4://": "socks4",
            "anytls://": "anytls", "juicity://": "juicity",
            "warp://": "warp",
            "dns://": "dns", "dnstt://": "dnstt",
        }
        for prefix, proto in _STANDARD_PROTOS.items():
            if line.startswith(prefix):
                result = self._parse_standard_uri(line, proto)
                result["raw"] = line
                return result
        return None

    def _decode_proxy_links(self, artifact_bytes: bytes) -> bytes:
        """Decode proxy URI lines into a human-readable JSON artifact."""
        try:
            text = artifact_bytes.decode("utf-8", errors="ignore")
        except (AttributeError, UnicodeDecodeError):
            return b""

        decoded_entries: List[Dict[str, Any]] = []
        protocols: Dict[str, int] = {}

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            entry = self._decode_single_line(line)
            if entry:
                proto = entry.get("protocol", "unknown")
                decoded_entries.append(entry)
                protocols[proto] = protocols.get(proto, 0) + 1

        if not decoded_entries:
            return b""

        result: Dict[str, Any] = {
            "total": len(decoded_entries),
            "protocols": protocols,
            "entries": decoded_entries,
        }
        return json.dumps(result, indent=2, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _reencode_as_base64_sub(artifact_bytes: bytes) -> bytes:
        """Re-encode proxy URI lines as a base64 blob (standard subscription format)."""
        try:
            text = artifact_bytes.decode("utf-8", errors="ignore").strip()
            if not text:
                return b""
            return base64.b64encode(text.encode("utf-8"))
        except (AttributeError, UnicodeDecodeError):
            return b""

    # ------------------------------------------------------------------

    def run(self, route_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build artifacts for a route. Returns list of build results (one per format)."""
        route_start = time.time()
        route_name = route_config["name"]
        formats = route_config["formats"]
        allowed_source_ids = route_config.get("from_sources", [])

        logger.info(
            f"[Build] ═══ Route '{route_name}' ═══  "
            f"formats={formats}  sources={len(allowed_source_ids)}"
        )

        fetch_start = time.time()
        records = self.state_repo.get_records_for_build(formats, allowed_source_ids)
        fetch_duration = time.time() - fetch_start
        record_count = len(records)

        # Count records per format type for diagnostics
        type_counts = {}
        for r in records:
            rt = r.get("record_type", "?")
            type_counts[rt] = type_counts.get(rt, 0) + 1

        logger.info(
            f"[Build] Fetched {record_count} records in {fetch_duration:.2f}s "
            f"from {len(allowed_source_ids)} sources  types={type_counts}"
        )

        if not records:
            logger.info(f"[Build] No records for route '{route_name}' — nothing to build.")
            return []

        results: List[Dict[str, Any]] = []
        built_formats = []
        empty_formats = []

        for fmt in formats:
            try:
                build_start = time.time()
                handler = self.registry.get(fmt)
                if not handler:
                    logger.error(f"[Build] No handler for format={fmt}, skipping.")
                    continue

                # Filter records to only those matching this format's record_type
                fmt_records = [r for r in records if r.get("record_type") == fmt]
                if not fmt_records:
                    empty_formats.append(fmt)
                    logger.debug(f"[Build] No records of type '{fmt}' for route '{route_name}'")
                    continue

                artifact_bytes = handler.build(fmt_records)
                build_duration = time.time() - build_start
                artifact_size_kb = len(artifact_bytes) / 1024

                if not artifact_bytes:
                    empty_formats.append(fmt)
                    logger.debug(f"[Build] Empty artifact for '{route_name}/{fmt}' — no matching records")
                    continue

                # Skip minimal/empty ZIP artifacts (opaque formats with no real content)
                if isinstance(artifact_bytes, (bytes, bytearray)) and len(artifact_bytes) <= _EMPTY_ZIP_THRESHOLD:
                    empty_formats.append(fmt)
                    logger.debug(
                        f"[Build] Minimal artifact for '{route_name}/{fmt}' "
                        f"({len(artifact_bytes)} bytes, likely empty ZIP) — skipping"
                    )
                    continue

                artifact_hash = self.artifact_store.save_artifact(route_name, fmt, artifact_bytes)
                self.artifact_store.save_output(route_name, fmt, artifact_bytes)
                built_formats.append(fmt)
                logger.info(
                    f"[Build] ✓ {route_name}/{fmt}: {artifact_size_kb:.1f} KB  "
                    f"build={build_duration:.2f}s  hash={artifact_hash[:12] if artifact_hash else 'N/A'}"
                )

                # Decode proxy links → decoded JSON artifact + base64 re-encoded subscription
                if fmt in ("npvt", "npvtsub"):
                    decoded = self._decode_proxy_links(artifact_bytes)
                    if decoded:
                        self.artifact_store.save_output(route_name, f"{fmt}.decoded.json", decoded)
                        dec_size_kb = len(decoded) / 1024
                        logger.info(
                            f"[Build] ✓ {route_name}/{fmt}.decoded.json: {dec_size_kb:.1f} KB  "
                            f"(structured JSON of all proxy URIs)"
                        )
                        results.append({
                            "route_name": route_name,
                            "format": f"{fmt}.decoded.json",
                            "unique_id": f"{route_name}:{fmt}.decoded.json",
                            "artifact_hash": artifact_hash + "_dec",
                            "data": decoded,
                            "count": record_count,
                        })

                    reencoded = self._reencode_as_base64_sub(artifact_bytes)
                    if reencoded:
                        self.artifact_store.save_output(route_name, f"{fmt}.b64sub", reencoded)
                        b64_size_kb = len(reencoded) / 1024
                        logger.info(
                            f"[Build] ✓ {route_name}/{fmt}.b64sub: {b64_size_kb:.1f} KB  "
                            f"(base64 subscription for v2rayN/v2rayNG)"
                        )
                        results.append({
                            "route_name": route_name,
                            "format": f"{fmt}.b64sub",
                            "unique_id": f"{route_name}:{fmt}.b64sub",
                            "artifact_hash": artifact_hash + "_b64",
                            "data": reencoded,
                            "count": record_count,
                        })

                unique_id = f"{route_name}:{fmt}"
                results.append(
                    {
                        "route_name": route_name,
                        "format": fmt,
                        "unique_id": unique_id,
                        "artifact_hash": artifact_hash,
                        "data": artifact_bytes,
                        "count": record_count,
                    }
                )
            except Exception as e:
                logger.exception(f"[Build] Failed for {route_name}/{fmt}: {e}")

        route_dur = time.time() - route_start
        logger.info(
            f"[Build] ═══ Route '{route_name}' done ═══  "
            f"artifacts={len(results)}  built=[{', '.join(built_formats)}]  "
            f"empty=[{', '.join(empty_formats) or 'none'}]  duration={route_dur:.2f}s"
        )
        return results
