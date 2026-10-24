import os
import base64
import json
import re
import math
import yaml
import shutil
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Optional

from huntx.core.router import _PROXY_SCHEMES

# Paths
DATA_DIR = Path(os.getenv("HUNTX_DATA_DIR", "persist/data")).resolve()
OUTPUT_DIR = DATA_DIR / "outputs"
DIST_DIR = DATA_DIR / "dist"

# Known binary format extensions (published as ZIP)
_ZIP_EXTENSIONS = {".ovpn", ".npv4", ".ehi", ".hc", ".hat", ".sip", ".nm", ".zip"}

# JSON files that describe the release rather than carrying proxy records, so
# they must not be reported as a decoded dataset.
_NON_PRODUCT_JSON = frozenset({
    "manifest.json",
    ".huntx-output-ownership.json",
    "empty-release.json",
    "v2ray_test_config.json",
})


def decode_base64_safe(data: str) -> str:
    missing_padding = len(data) % 4
    if missing_padding:
        data += "=" * (4 - missing_padding)
    return base64.b64decode(data).decode("utf-8", errors="ignore")


def parse_vmess(link: str) -> Optional[Dict[str, Any]]:
    """Parse vmess://... link into dict."""
    try:
        b64 = link[len("vmess://"):].split("#", 1)[0]
        json_str = decode_base64_safe(b64)
        return json.loads(json_str)
    except Exception as e:
        print(f"    Error parsing vmess: {e}")
        return None


def generate_v2ray_config(outbounds: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate a minimal V2Ray config with these outbounds."""
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [{"port": 1080, "protocol": "socks", "settings": {"auth": "noauth"}}],
        "outbounds": outbounds,
    }


def convert_vmess_to_outbound(vdata: Dict[str, Any]) -> Dict[str, Any]:
    """Convert parsed vmess dict to V2Ray outbound config."""
    return {
        "protocol": "vmess",
        "settings": {
            "vnext": [
                {
                    "address": vdata.get("add"),
                    "port": int(vdata.get("port", 443)),
                    "users": [
                        {"id": vdata.get("id"), "alterId": int(vdata.get("aid", 0)), "security": "auto", "level": 0}
                    ],
                }
            ]
        },
        "streamSettings": {"network": vdata.get("net", "tcp"), "security": vdata.get("tls", "none")},
        "tag": vdata.get("ps", "proxy"),
    }


def validate_text_file(path: Path) -> Dict[str, Any]:
    """Validate a text-based output file. Returns stats dict."""
    stats: Dict[str, Any] = {"type": "text", "lines": 0, "protocols": Counter(), "outbounds": []}

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        print(f"  ERROR: Could not read: {e}")
        stats["invalid"] = True
        return stats

    # Try base64 decode if it looks encoded
    clean = text.strip()
    if clean and " " not in clean and "://" not in clean:
        try:
            decoded = decode_base64_safe(clean)
            if any(decoded.startswith(s) or ("\n" + s) in decoded for s in _PROXY_SCHEMES[:5]):
                text = decoded
                print("  INFO: Decoded base64 content.")
        except Exception:
            pass

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    stats["lines"] = len(lines)

    for line in lines:
        for scheme in _PROXY_SCHEMES:
            if line.startswith(scheme):
                proto = scheme.rstrip(":/")
                stats["protocols"][proto] += 1
                if line.startswith("vmess://"):
                    vdata = parse_vmess(line)
                    if vdata:
                        stats["outbounds"].append(convert_vmess_to_outbound(vdata))
                break

    return stats


def validate_zip_file(path: Path) -> Dict[str, Any]:
    """Validate a ZIP archive output file. Returns stats dict."""
    stats: Dict[str, Any] = {"type": "zip", "entries": 0, "total_size": 0, "extensions": Counter()}

    try:
        with zipfile.ZipFile(path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                stats["entries"] += 1
                stats["total_size"] += info.file_size
                ext = Path(info.filename).suffix.lower()
                stats["extensions"][ext] += 1
    except zipfile.BadZipFile:
        print("  WARNING: Not a valid ZIP file.")
        stats["invalid"] = True
    except Exception as e:
        print(f"  ERROR: {e}")
        stats["invalid"] = True

    return stats


def _validate_json_shape(data: Any, kind: str) -> None:
    """Fail closed when a node feed and a runnable profile swap meanings."""
    if kind == "nekobox_nodes":
        if not isinstance(data, list):
            raise ValueError("NekoBox node feed must be a JSON array")
        nodes = data
    else:
        if not isinstance(data, dict):
            raise ValueError(f"{kind} requires a JSON object")
        if kind == "singbox_profile":
            if not isinstance(data.get("dns"), dict) or not isinstance(data.get("route"), dict):
                raise ValueError("Sing-box runnable profile must include DNS and route policy")
        if kind.endswith("_profile"):
            if not isinstance(data.get("inbounds"), list) or not data["inbounds"]:
                raise ValueError("Runnable profile must include nonempty inbounds")
        else:
            if set(data) != {"outbounds"}:
                raise ValueError("Independent-node subscription must contain only outbounds")
        nodes = data.get("outbounds")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError(f"{kind} requires a nonempty node list")
    if kind.endswith("_nodes"):
        protocol_key = "protocol" if kind == "xray_nodes" else "type"
        if any(
            not isinstance(node, dict)
            or not isinstance(node.get(protocol_key), str) or not node[protocol_key].strip()
            or not isinstance(node.get("tag"), str) or not node["tag"].strip()
            for node in nodes
        ):
            raise ValueError(f"{kind} contains a node without protocol/type and tag")
        tags = [node["tag"] for node in nodes]
        if len(set(tags)) != len(tags):
            raise ValueError(f"{kind} contains duplicate node tags")
        if protocol_key == "type" and any(
            node["type"] in {"selector", "urltest", "direct", "block", "dns"}
            for node in nodes
        ):
            raise ValueError(f"{kind} contains a non-proxy helper outbound")


def validate_json_file(path: Path, *, artifact_kind: str | None = None) -> Dict[str, Any]:
    """Validate JSON structure and, when declared, its client import contract."""
    stats: Dict[str, Any] = {"type": "json", "entries": 0, "protocols": Counter()}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if artifact_kind is not None:
            _validate_json_shape(data, artifact_kind)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and isinstance(data.get("outbounds"), list):
            # Sing-box/Xray subscription artifacts carry node arrays inside
            # outbounds-only objects. Count the children,
            # not the JSON document itself.
            items = list(data["outbounds"])
            endpoints = data.get("endpoints")
            if isinstance(endpoints, list):
                items.extend(endpoints)
        elif isinstance(data, dict) and isinstance(data.get("entries"), list):
            items = data["entries"]
        elif isinstance(data, dict):
            items = [data]
        else:
            items = []

        stats["entries"] = len(items)
        for entry in items:
            if not isinstance(entry, dict):
                continue
            proto = entry.get("protocol") or entry.get("type", "unknown")
            stats["protocols"][proto] += 1
    except (OSError, ValueError, TypeError) as e:
        print(f"  ERROR: Invalid JSON: {e}")
        stats["invalid"] = True

    return stats


def validate_clash_subscription(path: Path) -> Dict[str, Any]:
    """Validate HUNTX's proxies-only Mihomo provider without a YAML dependency."""
    stats: Dict[str, Any] = {"type": "clash.yaml", "entries": 0, "protocols": Counter()}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0].strip() != "proxies:":
            raise ValueError("Clash subscription must start with a proxies: list")
        parsed_yaml = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(parsed_yaml, dict) or set(parsed_yaml) != {"proxies"}:
            raise ValueError("Clash provider must contain only proxies")
        if not isinstance(parsed_yaml["proxies"], list):
            raise ValueError("Clash provider proxies must be an array")
        for line in lines[1:]:
            stripped = line.strip()
            if not stripped:
                continue
            if not stripped.startswith("- "):
                raise ValueError("Clash subscription contains profile-level YAML")
            item = json.loads(stripped[2:])
            if not isinstance(item, dict) or not item.get("name") or not item.get("type"):
                raise ValueError("Clash subscription contains an invalid proxy mapping")
            stats["entries"] += 1
            stats["protocols"][str(item["type"])] += 1
    except (OSError, ValueError, TypeError, yaml.YAMLError) as e:
        print(f"  ERROR: Invalid Clash subscription: {e}")
        stats["invalid"] = True
    return stats


def validate_gate_report(path: Path) -> Dict[str, Any]:
    """Verify the candidate disposition ledger conserves every identity."""
    stats: Dict[str, Any] = {"type": "health_gate", "entries": 0}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, dict) or report.get("schema_version") != 1:
            raise ValueError("invalid health gate schema")
        n, accepted, rejected = (
            report.get("candidates"), report.get("admitted"), report.get("rejected")
        )
        if (any(type(v) is not int or v < 0 for v in (n, accepted, rejected))
                or accepted + rejected != n):
            raise ValueError("health gate totals do not reconcile")
        identities, reasons = report.get("identities"), report.get("reasons")
        if (not isinstance(identities, dict) or len(identities) != n
                or not isinstance(reasons, dict)
                or sum(reasons.values()) != n
                or reasons.get("admitted", 0) != accepted):
            raise ValueError("health gate dispositions do not reconcile")
        for digest, reason in identities.items():
            if (not isinstance(digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                    or not isinstance(reason, str) or reason not in reasons):
                raise ValueError("invalid health-gate identity row")
        stats["entries"] = n
    except (OSError, ValueError, TypeError) as error:
        print(f"  ERROR: Invalid health gate: {error}")
        stats["invalid"] = True
    return stats


def validate_coverage_report(path: Path) -> Dict[str, Any]:
    """Reject fabricated or incomplete client conversion coverage matrices."""
    stats: Dict[str, Any] = {"type": "format_coverage", "entries": 0}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise ValueError("invalid client coverage schema")
        identities = document.get("identities")
        formats = document.get("formats")
        n = document.get("admitted_count")
        if (type(n) is not int or n < 0 or not isinstance(identities, dict)
                or len(identities) != n or not isinstance(formats, dict)
                or set(formats) != {"singbox", "xray", "nekobox", "clash"}):
            raise ValueError("invalid coverage identities/formats")
        for name, totals in formats.items():
            if (not isinstance(totals, dict)
                    or type(totals.get("represented")) is not int
                    or type(totals.get("omitted")) is not int
                    or totals["represented"] + totals["omitted"] != n):
                raise ValueError(f"{name}: client coverage does not conserve nodes")
        for digest, row in identities.items():
            if (not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                    or not isinstance(row, dict)
                    or not isinstance(row.get("formats"), dict)
                    or set(row["formats"]) != set(formats)):
                raise ValueError("invalid per-proxy coverage row")
        stats["entries"] = n
    except (OSError, ValueError, TypeError) as error:
        print(f"  ERROR: Invalid client coverage: {error}")
        stats["invalid"] = True
    return stats


def validate_health_sidecar(path: Path) -> Dict[str, Any]:
    """Check the private-data-free, identity-keyed publication attestation."""
    stats: Dict[str, Any] = {"type": "health_sidecar", "entries": 0}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(document, dict)
                or document.get("schema_version") != 1
                or document.get("evidence") != "publisher_authenticated_https"):
            raise ValueError("invalid publisher evidence schema")
        records = document.get("records")
        if not isinstance(records, dict) or document.get("admitted_count") != len(records):
            raise ValueError("authenticated sidecar count mismatch")
        for digest, values in records.items():
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError("invalid semantic connection digest")
            if not isinstance(values, dict):
                raise ValueError("invalid evidence entry")
            measured = [values.get(key) for key in ("checked_at", "expires_at", "duration_ms")]
            if any(type(value) not in (int, float) or not math.isfinite(value) for value in measured):
                raise ValueError("missing or non-finite authenticated probe measurement")
            checked, expires, duration = measured
            if not 0 <= duration <= 30000 or not checked <= expires:
                raise ValueError("invalid authenticated evidence timestamps")
        stats["entries"] = len(records)
    except (OSError, ValueError, TypeError) as error:
        print(f"  ERROR: Invalid authenticated evidence: {error}")
        stats["invalid"] = True
    return stats


def _matches_derived_name(name: str, dotted: str, canonical: str) -> bool:
    """Match artifact-store dotted names and canonical exported filenames."""
    return name.endswith(dotted) or name.endswith(canonical)


def validate_file(path: Path) -> Dict[str, Any]:
    """Route validation to the right handler based on file type."""
    name = path.name.lower()
    size = path.stat().st_size
    size_kb = size / 1024

    print(f"\n  {path.name}  ({size_kb:.1f} KB)")

    if size == 0:
        print("    WARNING: Empty file.")
        return {"type": "empty"}

    # Specific product shapes first. A blanket ".json" test placed ahead of them
    # reported every profile as a decoded dataset, and one placed behind them
    # never ran for the canonical "<route>.json" the rename introduced.
    if (_matches_derived_name(name, ".singbox.profile.json", "_singbox_profile.json")
            or _matches_derived_name(name, ".singbox.json", "_singbox.json")):
        stats = validate_json_file(path, artifact_kind="singbox_profile")
        print(f"    sing-box full profile: {size_kb:.1f} KB")
        return stats

    if (_matches_derived_name(name, ".xray.profile.json", "_xray_profile.json")
            or _matches_derived_name(name, ".xray.json", "_xray.json")):
        stats = validate_json_file(path, artifact_kind="xray_profile")
        print(f"    Xray full profile: {size_kb:.1f} KB")
        return stats

    if _matches_derived_name(name, ".singbox.nodes.json", "_singbox_nodes.json"):
        stats = validate_json_file(path, artifact_kind="singbox_nodes")
        print(f"    sing-box subscription: {stats['entries']} nodes  {size_kb:.1f} KB")
        return stats

    if _matches_derived_name(name, ".xray.nodes.json", "_xray_nodes.json"):
        stats = validate_json_file(path, artifact_kind="xray_nodes")
        print(f"    Xray subscription: {stats['entries']} nodes  {size_kb:.1f} KB")
        return stats

    if _matches_derived_name(name, ".nekobox.json", "_nekobox.json"):
        stats = validate_json_file(path, artifact_kind="nekobox_nodes")
        print(f"    NekoBox subscription: {stats['entries']} nodes  {size_kb:.1f} KB")
        return stats

    if _matches_derived_name(name, ".health.json", "_health.json"):
        stats = validate_health_sidecar(path)
        return stats

    if _matches_derived_name(name, ".gate.json", "_gate.json"):
        return validate_gate_report(path)

    if _matches_derived_name(name, ".coverage.json", "_coverage.json"):
        return validate_coverage_report(path)

    if _matches_derived_name(name, ".clash.yaml", "_clash.yaml"):
        stats = validate_clash_subscription(path)
        print(f"    Clash/Mihomo subscription: {stats['entries']} nodes  {size_kb:.1f} KB")
        return stats

    if name.endswith(".b64sub") or name.endswith("_b64sub.txt") or name.endswith("_base64.txt"):
        print(f"    Base64 subscription: {size_kb:.1f} KB")
        return {"type": "b64sub", "size": size}

    if name.endswith(".json") and name not in _NON_PRODUCT_JSON:
        stats = validate_json_file(path)
        if stats["entries"]:
            protos = ", ".join(f"{k}:{v}" for k, v in stats["protocols"].most_common(10))
            print(f"    JSON: {stats['entries']} entries  protocols=[{protos}]")
        return stats

    suffix = path.suffix.lower()
    if suffix in _ZIP_EXTENSIONS:
        stats = validate_zip_file(path)
        if stats["entries"]:
            exts = ", ".join(f"{k}:{v}" for k, v in stats["extensions"].most_common(10))
            print(
                f"    ZIP: {stats['entries']} files  {stats['total_size'] / 1024:.1f} KB uncompressed  types=[{exts}]"
            )
        return stats

    # Default: treat as text
    stats = validate_text_file(path)
    if stats["protocols"]:
        protos = ", ".join(f"{k}:{v}" for k, v in stats["protocols"].most_common(10))
        print(f"    Text: {stats['lines']} lines  protocols=[{protos}]")
    elif stats["lines"]:
        print(f"    Text: {stats['lines']} lines (no proxy URIs detected)")
    return stats


def _prepare_verified_dist(staged: Path) -> tuple[int, int, Counter]:
    """Copy first, then validate those exact bytes before publication.

    Copying only after checking source files left a race where a generated
    file could change between validation and distribution. Flattening nested
    output paths is historically supported, but duplicate basenames must be
    rejected rather than silently overwriting another source's contents.
    """
    all_outbounds: List[Dict[str, Any]] = []
    invalid_files: list[str] = []
    seen_names: set[str] = set()
    file_count = 0
    total_size = 0
    format_counts: Counter = Counter()
    staged_outputs = 0
    print("\n── Validating output files ──")

    for item in sorted(OUTPUT_DIR.rglob("*")):
        if item.is_symlink():
            raise RuntimeError(f"Refusing symlinked generated output: {item}")
        if not item.is_file():
            continue
        if item.name in seen_names:
            raise RuntimeError(f"Conflicting generated output filename: {item.name}")
        if item.name in {"verify_output.py", "v2ray_test_config.json"}:
            raise RuntimeError(f"Generated output conflicts with a verifier-owned name: {item.name}")
        seen_names.add(item.name)
        staged_file = staged / item.name
        # The source may be modified while validation runs, so validate the
        # immutable staged copy rather than the original input path.
        shutil.copy2(item, staged_file)
        stats = validate_file(staged_file)
        if stats.get("invalid"):
            invalid_files.append(item.name)
        if staged_file.stat().st_size == 0:
            staged_file.unlink()
        else:
            staged_outputs += 1
        file_count += 1
        size = item.stat().st_size
        total_size += size

        # Track format, in the same precedence order as validate_file so the
        # counts and the per-file report never disagree. The base64 test has to
        # precede the blanket ".txt" one or the base64 feed is counted as a raw
        # URI list, and the canonical "<route>.json" has to be recognised or the
        # decoded dataset is not counted at all.
        name = item.name.lower()
        suffix = item.suffix.lower()
        if (
            _matches_derived_name(name, ".singbox.profile.json", "_singbox_profile.json")
            or _matches_derived_name(name, ".singbox.json", "_singbox.json")
        ):
            format_counts["singbox.profile.json"] += 1
        elif (
            _matches_derived_name(name, ".xray.profile.json", "_xray_profile.json")
            or _matches_derived_name(name, ".xray.json", "_xray.json")
        ):
            format_counts["xray.profile.json"] += 1
        elif _matches_derived_name(name, ".singbox.nodes.json", "_singbox_nodes.json"):
            format_counts["singbox.json"] += 1
        elif _matches_derived_name(name, ".xray.nodes.json", "_xray_nodes.json"):
            format_counts["xray.json"] += 1
        elif _matches_derived_name(name, ".nekobox.json", "_nekobox.json"):
            format_counts["nekobox.json"] += 1
        elif _matches_derived_name(name, ".clash.yaml", "_clash.yaml"):
            format_counts["clash.yaml"] += 1
        elif _matches_derived_name(name, ".health.json", "_health.json"):
            format_counts["health.json"] += 1
        elif _matches_derived_name(name, ".coverage.json", "_coverage.json"):
            format_counts["coverage.json"] += 1
        elif _matches_derived_name(name, ".gate.json", "_gate.json"):
            format_counts["gate.json"] += 1
        elif name.endswith(".b64sub") or name.endswith("_b64sub.txt") or name.endswith("_base64.txt"):
            format_counts["b64sub"] += 1
        elif (
            name.endswith(".decoded.json")
            or name.endswith("_decoded.json")
            or (name.endswith(".json") and name not in _NON_PRODUCT_JSON)
        ):
            format_counts["decoded.json"] += 1
        elif name.endswith(".txt"):
            format_counts["raw.txt"] += 1
        else:
            format_counts[suffix or "unknown"] += 1

        if stats.get("outbounds"):
            all_outbounds.extend(stats["outbounds"])

    if invalid_files:
        raise RuntimeError(
            "Output verification failed, refusing to publish malformed artifacts: "
            + ", ".join(sorted(invalid_files))
        )
    if not staged_outputs:
        raise RuntimeError("Output verification found no nonempty release artifacts")
    # Build helper files only after all generated products have been verified.
    shutil.copy2(__file__, staged / "verify_output.py")
    if all_outbounds:
        config = generate_v2ray_config(all_outbounds)
        (staged / "v2ray_test_config.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8"
        )
    return file_count, total_size, format_counts


def _install_verified_dist(staged: Path) -> None:
    """Replace distribution as a directory, rolling back on rename failure."""
    previous = staged.parent / "previous"
    moved_old = False
    if DIST_DIR.is_symlink() or (DIST_DIR.exists() and not DIST_DIR.is_dir()):
        raise RuntimeError(f"Refusing non-directory distribution target: {DIST_DIR}")
    if DIST_DIR.exists():
        os.replace(DIST_DIR, previous)
        moved_old = True
    try:
        os.replace(staged, DIST_DIR)
    except BaseException:
        if moved_old:
            os.replace(previous, DIST_DIR)
        raise


def main() -> None:
    """Verify every output and publish the entire distribution or none of it."""
    print("═══ HUNTX Output Verification ═══")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Dist:   {DIST_DIR}")
    if not OUTPUT_DIR.is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {OUTPUT_DIR}")
    resolved_dist = DIST_DIR.resolve()
    if DIST_DIR.is_symlink() or resolved_dist.name.lower() != "dist" or len(resolved_dist.parts) < 3:
        raise RuntimeError(f"Refusing unsafe distribution target: {DIST_DIR}")
    DIST_DIR.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".huntx-dist-verify-", dir=DIST_DIR.parent) as scratch:
        staged = Path(scratch) / "prepared"
        staged.mkdir()
        file_count, total_size, format_counts = _prepare_verified_dist(staged)
        _install_verified_dist(staged)
    print("\n── Summary ──")
    print(f"Files: {file_count}  Total size: {total_size / 1024:.1f} KB")
    fmts = ", ".join(f"{k}:{v}" for k, v in format_counts.most_common())
    print(f"Formats: [{fmts}]")
    print(f"Verified artifacts published to {DIST_DIR}")


if __name__ == "__main__":
    main()
