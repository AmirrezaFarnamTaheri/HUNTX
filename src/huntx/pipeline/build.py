from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import time
from collections import defaultdict
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

from ..formats.common.singbox import build_singbox_config_bytes
from ..formats.registry import FormatRegistry
from ..state.repo import StateRepo
from ..store.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)

_STANDARD_PROTOCOLS = {
    "vless": "vless",
    "trojan": "trojan",
    "hysteria2": "hysteria2",
    "hy2": "hysteria2",
    "hysteria": "hysteria",
    "tuic": "tuic",
    "wireguard": "wireguard",
    "wg": "wireguard",
    "socks": "socks",
    "socks5": "socks5",
    "socks4": "socks4",
    "anytls": "anytls",
    "juicity": "juicity",
    "warp": "warp",
    "dns": "dns",
    "dnstt": "dnstt",
}
_DERIVED_PROXY_FORMATS = frozenset({"npvt", "npvtsub"})


class BuildPipeline:
    def __init__(
        self,
        state_repo: StateRepo,
        artifact_store: ArtifactStore,
        registry: FormatRegistry,
        *,
        format_locks: Optional[dict[str, threading.Lock]] = None,
        format_locks_guard: Optional[threading.Lock] = None,
    ) -> None:
        self.state_repo = state_repo
        self.artifact_store = artifact_store
        self.registry = registry
        self._format_locks = format_locks if format_locks is not None else {}
        self._format_locks_guard = format_locks_guard or threading.Lock()

    def _format_lock(self, format_id: str) -> threading.Lock:
        with self._format_locks_guard:
            lock = self._format_locks.get(format_id)
            if lock is None:
                lock = threading.Lock()
                self._format_locks[format_id] = lock
            return lock

    @staticmethod
    def _b64_decode(data: str) -> str:
        """Base64 decode with auto-padding, including URL-safe variants."""
        normalized = data.replace("-", "+").replace("_", "/")
        normalized += "=" * ((4 - len(normalized) % 4) % 4)
        return base64.b64decode(normalized).decode("utf-8", errors="ignore")

    @staticmethod
    def _parse_standard_uri(line: str, protocol: str) -> dict[str, Any]:
        try:
            parsed = urlparse(line)
            params = {key: values[0] if len(values) == 1 else values for key, values in parse_qs(parsed.query).items()}
            result: dict[str, Any] = {"protocol": protocol}
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
    def _decode_vmess(line: str) -> dict[str, Any]:
        try:
            obj = json.loads(BuildPipeline._b64_decode(line[8:]))
            return {"protocol": "vmess", "decoded": obj, "raw": line}
        except Exception:
            return {"protocol": "vmess", "raw": line, "error": "decode_failed"}

    @staticmethod
    def _decode_ss(line: str) -> dict[str, Any]:
        try:
            rest = line[5:]
            tag = ""
            if "#" in rest:
                rest, tag = rest.rsplit("#", 1)
                tag = unquote(tag)

            if "@" in rest:
                userinfo, hostport = rest.rsplit("@", 1)
                try:
                    decoded_ui = BuildPipeline._b64_decode(userinfo)
                    method, password = decoded_ui.split(":", 1) if ":" in decoded_ui else (decoded_ui, "")
                except Exception:
                    parts = unquote(userinfo).split(":", 1)
                    method = parts[0]
                    password = parts[1] if len(parts) > 1 else ""
                host_parts = hostport.split("?", 1)[0]
                host, port_s = host_parts.rsplit(":", 1) if ":" in host_parts else (host_parts, "0")
                return {
                    "protocol": "shadowsocks",
                    "method": method,
                    "password": password,
                    "address": host,
                    "port": int(port_s),
                    "tag": tag,
                    "raw": line,
                }

            decoded = BuildPipeline._b64_decode(rest.split("?", 1)[0])
            if "@" in decoded:
                method_password, host_port = decoded.rsplit("@", 1)
                method, password = method_password.split(":", 1) if ":" in method_password else (method_password, "")
                host, port_s = host_port.rsplit(":", 1) if ":" in host_port else (host_port, "0")
                return {
                    "protocol": "shadowsocks",
                    "method": method,
                    "password": password,
                    "address": host,
                    "port": int(port_s),
                    "tag": tag,
                    "raw": line,
                }
            return {
                "protocol": "shadowsocks",
                "raw": line,
                "decoded_text": decoded,
            }
        except Exception:
            return {"protocol": "shadowsocks", "raw": line, "error": "decode_failed"}

    @staticmethod
    def _decode_ssr(line: str) -> dict[str, Any]:
        try:
            decoded = BuildPipeline._b64_decode(line[6:])
            main_part, _, param_part = decoded.partition("/?")
            parts = main_part.split(":")
            if len(parts) >= 6:
                server = ":".join(parts[:-5])
                port, protocol, method, obfs, b64pass = parts[-5:]
                result: dict[str, Any] = {
                    "protocol": "shadowsocksr",
                    "server": server,
                    "port": int(port),
                    "ssr_protocol": protocol,
                    "method": method,
                    "obfs": obfs,
                    "password": BuildPipeline._b64_decode(b64pass),
                }
                if param_part:
                    for item in param_part.split("&"):
                        if "=" not in item:
                            continue
                        key, value = item.split("=", 1)
                        try:
                            result[key] = BuildPipeline._b64_decode(value)
                        except Exception:
                            result[key] = value
                result["raw"] = line
                return result
            return {
                "protocol": "shadowsocksr",
                "raw": line,
                "decoded_text": decoded,
            }
        except Exception:
            return {"protocol": "shadowsocksr", "raw": line, "error": "decode_failed"}

    def _decode_single_line(self, line: str) -> Optional[dict[str, Any]]:
        scheme, separator, _ = line.partition("://")
        if not separator:
            return None
        normalized_scheme = scheme.lower()
        if normalized_scheme == "vmess":
            return self._decode_vmess(line)
        if normalized_scheme == "ss":
            return self._decode_ss(line)
        if normalized_scheme == "ssr":
            return self._decode_ssr(line)
        protocol = _STANDARD_PROTOCOLS.get(normalized_scheme)
        if protocol is None:
            return None
        result = self._parse_standard_uri(line, protocol)
        result["raw"] = line
        return result

    def _decode_proxy_text(self, text: str) -> bytes:
        decoded_entries: list[dict[str, Any]] = []
        protocols: dict[str, int] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            entry = self._decode_single_line(line)
            if entry is None:
                continue
            protocol = str(entry.get("protocol", "unknown"))
            decoded_entries.append(entry)
            protocols[protocol] = protocols.get(protocol, 0) + 1
        if not decoded_entries:
            return b""
        payload = {
            "total": len(decoded_entries),
            "protocols": protocols,
            "entries": decoded_entries,
        }
        return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")

    def _decode_proxy_links(self, artifact_bytes: bytes) -> bytes:
        try:
            text = artifact_bytes.decode("utf-8", errors="ignore")
        except (AttributeError, UnicodeDecodeError):
            return b""
        return self._decode_proxy_text(text)

    @staticmethod
    def _reencode_as_base64_sub(artifact_bytes: bytes) -> bytes:
        try:
            text = artifact_bytes.decode("utf-8", errors="ignore").strip()
        except (AttributeError, UnicodeDecodeError):
            return b""
        return base64.b64encode(text.encode("utf-8")) if text else b""

    def _proxy_derivatives(self, artifact_bytes: bytes) -> tuple[bytes, bytes, bytes]:
        """Create decoded JSON, base64 subscription and sing-box config from one UTF-8 decode.

        The sing-box config is empty bytes when no proxy URI parses, so callers can skip
        emitting an empty derivative.
        """
        try:
            text = artifact_bytes.decode("utf-8", errors="ignore")
        except (AttributeError, UnicodeDecodeError):
            return b"", b"", b""
        stripped = text.strip()
        if not stripped:
            return b"", b"", b""
        return (
            self._decode_proxy_text(text),
            base64.b64encode(stripped.encode("utf-8")),
            build_singbox_config_bytes(text),
        )

    def run(
        self,
        route_config: dict[str, Any],
        *,
        records: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        """Build one route with a single record grouping pass."""
        route_start = time.monotonic()
        route_name = str(route_config["name"])
        formats = list(dict.fromkeys(str(fmt) for fmt in route_config["formats"]))
        allowed_source_ids = list(dict.fromkeys(route_config.get("from_sources", [])))
        min_seen_file_id = route_config.get("min_seen_file_id")

        logger.info(
            "[Build] route=%s formats=%s sources=%s delta_seen_files_id>%s",
            route_name,
            formats,
            len(allowed_source_ids),
            min_seen_file_id if min_seen_file_id is not None else "all",
        )

        fetch_start = time.monotonic()
        if records is None:
            records = self.state_repo.get_records_for_build(
                formats,
                allowed_source_ids,
                min_seen_file_id=min_seen_file_id,
            )
        fetch_duration = time.monotonic() - fetch_start

        records_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            record_type = record.get("record_type")
            if isinstance(record_type, str):
                records_by_type[record_type].append(record)
        type_counts = {key: len(value) for key, value in records_by_type.items()}
        record_count = len(records)

        logger.info(
            "[Build] route=%s fetched=%s fetch_seconds=%.3f types=%s",
            route_name,
            record_count,
            fetch_duration,
            type_counts,
        )
        if not records:
            return []

        results: list[dict[str, Any]] = []
        built_formats: list[str] = []
        empty_formats: list[str] = []
        total_build_seconds = 0.0

        for format_id in formats:
            format_records = records_by_type.get(format_id, [])
            if not format_records:
                empty_formats.append(format_id)
                continue
            handler = self.registry.get(format_id)
            if handler is None:
                logger.error("[Build] No handler for format=%s", format_id)
                continue

            try:
                build_start = time.monotonic()
                with self._format_lock(format_id):
                    artifact_bytes = handler.build(format_records)
                build_duration = time.monotonic() - build_start
                total_build_seconds += build_duration
                if not artifact_bytes:
                    empty_formats.append(format_id)
                    continue

                artifact_hash = self.artifact_store.save_artifact(route_name, format_id, artifact_bytes)
                self.artifact_store.save_output(route_name, format_id, artifact_bytes)
                built_formats.append(format_id)
                format_count = len(format_records)

                if format_id in _DERIVED_PROXY_FORMATS:
                    decoded, reencoded, singbox = self._proxy_derivatives(artifact_bytes)
                    if decoded:
                        derived_format = f"{format_id}.decoded.json"
                        self.artifact_store.save_output(route_name, derived_format, decoded)
                        results.append(
                            {
                                "route_name": route_name,
                                "format": derived_format,
                                "unique_id": f"{route_name}:{derived_format}",
                                "artifact_hash": hashlib.sha256(decoded).hexdigest(),
                                "data": decoded,
                                "count": format_count,
                            }
                        )
                    if reencoded:
                        derived_format = f"{format_id}.b64sub"
                        self.artifact_store.save_output(route_name, derived_format, reencoded)
                        results.append(
                            {
                                "route_name": route_name,
                                "format": derived_format,
                                "unique_id": f"{route_name}:{derived_format}",
                                "artifact_hash": hashlib.sha256(reencoded).hexdigest(),
                                "data": reencoded,
                                "count": format_count,
                            }
                        )
                    if singbox:
                        derived_format = f"{format_id}.singbox.json"
                        self.artifact_store.save_output(route_name, derived_format, singbox)
                        results.append(
                            {
                                "route_name": route_name,
                                "format": derived_format,
                                "unique_id": f"{route_name}:{derived_format}",
                                "artifact_hash": hashlib.sha256(singbox).hexdigest(),
                                "data": singbox,
                                "count": format_count,
                            }
                        )

                results.append(
                    {
                        "route_name": route_name,
                        "format": format_id,
                        "unique_id": f"{route_name}:{format_id}",
                        "artifact_hash": artifact_hash,
                        "data": artifact_bytes,
                        "count": format_count,
                    }
                )
                logger.info(
                    "[Build] route=%s format=%s records=%s bytes=%s build_seconds=%.3f hash=%s",
                    route_name,
                    format_id,
                    format_count,
                    len(artifact_bytes),
                    build_duration,
                    artifact_hash[:12] if artifact_hash else "N/A",
                )
            except Exception:
                logger.exception("[Build] Failed for %s/%s", route_name, format_id)

        route_duration = time.monotonic() - route_start
        logger.info(
            "[Build] route=%s artifacts=%s built=%s empty=%s fetch_seconds=%.3f build_seconds=%.3f total_seconds=%.3f",
            route_name,
            len(results),
            built_formats,
            empty_formats,
            fetch_duration,
            total_build_seconds,
            route_duration,
        )
        return results
