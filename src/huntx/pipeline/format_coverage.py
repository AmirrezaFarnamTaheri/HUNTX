"""Identity-keyed, credential-free reconciliation of exported proxy node formats.

Do not treat an unsupported client conversion as an ingestion loss. Each
admitted connection must either appear in the final client subscription or
receive an explicit, auditable reason for its absence.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from ..formats.common.clash import build_clash_subscription_bytes
from ..formats.common.nekobox import build_nekobox_outbounds_bytes
from ..formats.common.singbox import build_singbox_config_bytes, parse_proxy_uri
from ..formats.common.xray import build_xray_config_bytes, omission_reason
from ..formats.npvt import canonical_proxy_identity


def _nodes(payload: bytes, fmt: str) -> list[dict[str, Any]]:
    if not payload:
        return []
    if fmt == "clash":
        lines = payload.decode("utf-8").splitlines()
        if not lines or lines[0] != "proxies:":
            raise ValueError("Clash provider is not a proxies-only list")
        return [json.loads(line.strip()[2:]) for line in lines[1:] if line.strip()]
    parsed = json.loads(payload)
    nodes: Any
    if fmt == "nekobox":
        if not isinstance(parsed, list):
            raise ValueError("NekoBox output is not an array")
        nodes = parsed
    else:
        if not isinstance(parsed, dict):
            raise ValueError(f"{fmt} output is not an object")
        nodes = parsed.get("outbounds")
    if not isinstance(nodes, list) or any(not isinstance(node, dict) for node in nodes):
        raise ValueError(f"{fmt} output has invalid node entries")
    return nodes


def _name(node: dict[str, Any], fmt: str) -> str:
    value = node.get("name" if fmt == "clash" else "tag")
    if not isinstance(value, str) or not value:
        raise ValueError(f"{fmt} contains an unnamed connection")
    return value


def _signature(node: dict[str, Any], fmt: str) -> str:
    relevant = {key: value for key, value in node.items() if key not in {"tag", "name"}}
    return json.dumps(relevant, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


_BUILD_ONE = {
    "singbox": build_singbox_config_bytes,
    "xray": build_xray_config_bytes,
    "nekobox": build_nekobox_outbounds_bytes,
    "clash": build_clash_subscription_bytes,
}


def build_client_coverage_report(
    text: str, *, singbox: bytes, xray: bytes, nekobox: bytes, clash: bytes
) -> bytes:
    """Reconcile each final format without recording secrets or raw proxy URIs."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    identities: dict[str, dict[str, Any]] = {}
    known_tags: set[str] = set()
    for line in lines:
        node = parse_proxy_uri(line)
        identity = canonical_proxy_identity(line)
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        if digest in identities:
            raise ValueError("Primary proxy feed contains duplicate canonical connections")
        tag = node.tag if node else None
        if tag is not None and tag in known_tags:
            raise ValueError("Primary feed has duplicate client-visible names")
        if tag is not None:
            known_tags.add(tag)
        identities[digest] = {
            "protocol": node.type if node else line.partition("://")[0].lower(),
            "_tag": tag, "_line": line, "formats": {},
        }

    payloads = {"singbox": singbox, "xray": xray, "nekobox": nekobox, "clash": clash}
    stats: dict[str, dict[str, Any]] = {}
    for fmt, payload in payloads.items():
        exported = _nodes(payload, fmt)
        exported_names = [_name(node, fmt) for node in exported]
        if len(set(exported_names)) != len(exported_names):
            raise ValueError(f"{fmt} output has duplicate proxy names")
        unexpected = set(exported_names) - known_tags
        if unexpected:
            raise ValueError(f"{fmt} contains unmatched exported connection tags")
        names = set(exported_names)
        signatures = {_signature(node, fmt) for node in exported}
        reasons: Counter[str] = Counter()
        represented = 0
        for record in identities.values():
            tag = record["_tag"]
            if tag is not None and tag in names:
                record["formats"][fmt] = {"status": "represented"}
                represented += 1
                continue
            raw = record["_line"]
            singly = _nodes(_BUILD_ONE[fmt](raw), fmt)
            if not singly:
                if fmt == "xray":
                    reason = omission_reason(raw, parse_proxy_uri(raw))
                else:
                    reason = "protocol_or_configuration_not_representable"
                status = "unsupported"
            elif any(_signature(node, fmt) in signatures for node in singly):
                reason = "duplicate_connection_after_conversion"
                status = "deduped_after_conversion"
            else:
                raise ValueError(f"{fmt} unexplained omission of representable proxy")
            record["formats"][fmt] = {"status": status, "reason": reason}
            reasons[reason] += 1

        if represented != len(exported):
            raise ValueError(f"{fmt} represented count differs from actual output")
        if represented + sum(reasons.values()) != len(identities):
            raise ValueError(f"{fmt} coverage count is not conserved")
        stats[fmt] = {
            "represented": represented, "omitted": len(identities) - represented,
            "reasons": dict(sorted(reasons.items())),
        }

    public = {
        digest: {"protocol": item["protocol"], "formats": item["formats"]}
        for digest, item in identities.items()
    }
    report = {
        "schema_version": 1,
        "identity_algorithm": "sha256-of-canonical-proxy-identity",
        "admitted_count": len(identities),
        "formats": stats,
        "identities": public,
    }
    return json.dumps(report, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":")).encode("utf-8")
