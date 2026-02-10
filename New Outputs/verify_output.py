import os
import base64
import json
import shutil
import subprocess
import zipfile
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Optional

# Paths
DATA_DIR = Path(os.getenv("HUNTX_DATA_DIR", "persist/data")).resolve()
OUTPUT_DIR = DATA_DIR / "output"
DIST_DIR = DATA_DIR / "dist"

# All known proxy URI schemes
_PROXY_SCHEMES = (
    "vmess://", "vless://", "trojan://", "ss://", "ssr://",
    "hysteria2://", "hy2://", "hysteria://", "tuic://",
    "wireguard://", "wg://", "socks://", "socks5://", "socks4://",
    "anytls://", "juicity://", "warp://", "dns://", "dnstt://",
)

# Known binary format extensions (published as ZIP)
_ZIP_EXTENSIONS = {".ovpn", ".npv4", ".ehi", ".hc", ".hat", ".sip", ".nm", ".zip"}


def decode_base64_safe(data: str) -> str:
    missing_padding = len(data) % 4
    if missing_padding:
        data += '=' * (4 - missing_padding)
    return base64.b64decode(data).decode("utf-8", errors="ignore")


def parse_vmess(link: str) -> Optional[Dict[str, Any]]:
    """Parse vmess://... link into dict."""
    try:
        b64 = link.replace("vmess://", "")
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
        "outbounds": outbounds
    }


def convert_vmess_to_outbound(vdata: Dict[str, Any]) -> Dict[str, Any]:
    """Convert parsed vmess dict to V2Ray outbound config."""
    return {
        "protocol": "vmess",
        "settings": {
            "vnext": [{
                "address": vdata.get("add"),
                "port": int(vdata.get("port", 443)),
                "users": [{
                    "id": vdata.get("id"),
                    "alterId": int(vdata.get("aid", 0)),
                    "security": "auto",
                    "level": 0
                }]
            }]
        },
        "streamSettings": {
            "network": vdata.get("net", "tcp"),
            "security": vdata.get("tls", "none")
        },
        "tag": vdata.get("ps", "proxy")
    }


def validate_text_file(path: Path) -> Dict[str, Any]:
    """Validate a text-based output file. Returns stats dict."""
    stats: Dict[str, Any] = {"type": "text", "lines": 0, "protocols": Counter(), "outbounds": []}

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"  ERROR: Could not read: {e}")
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

    lines = [l.strip() for l in text.splitlines() if l.strip()]
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
    except Exception as e:
        print(f"  ERROR: {e}")

    return stats


def validate_json_file(path: Path) -> Dict[str, Any]:
    """Validate a decoded JSON artifact."""
    stats: Dict[str, Any] = {"type": "json", "entries": 0, "protocols": Counter()}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            stats["entries"] = len(data)
            for entry in data:
                proto = entry.get("protocol", "unknown")
                stats["protocols"][proto] += 1
        elif isinstance(data, dict):
            stats["entries"] = 1
    except Exception as e:
        print(f"  ERROR: Invalid JSON: {e}")

    return stats


def validate_file(path: Path) -> Dict[str, Any]:
    """Route validation to the right handler based on file type."""
    name = path.name.lower()
    size = path.stat().st_size
    size_kb = size / 1024

    print(f"\n  {path.name}  ({size_kb:.1f} KB)")

    if size == 0:
        print("    WARNING: Empty file.")
        return {"type": "empty"}

    if name.endswith(".decoded.json"):
        stats = validate_json_file(path)
        if stats["entries"]:
            protos = ", ".join(f"{k}:{v}" for k, v in stats["protocols"].most_common(10))
            print(f"    JSON: {stats['entries']} entries  protocols=[{protos}]")
        return stats

    if name.endswith(".b64sub"):
        print(f"    Base64 subscription: {size_kb:.1f} KB")
        return {"type": "b64sub", "size": size}

    suffix = path.suffix.lower()
    if suffix in _ZIP_EXTENSIONS:
        stats = validate_zip_file(path)
        if stats["entries"]:
            exts = ", ".join(f"{k}:{v}" for k, v in stats["extensions"].most_common(10))
            print(f"    ZIP: {stats['entries']} files  {stats['total_size'] / 1024:.1f} KB uncompressed  types=[{exts}]")
        return stats

    # Default: treat as text
    stats = validate_text_file(path)
    if stats["protocols"]:
        protos = ", ".join(f"{k}:{v}" for k, v in stats["protocols"].most_common(10))
        print(f"    Text: {stats['lines']} lines  protocols=[{protos}]")
    elif stats["lines"]:
        print(f"    Text: {stats['lines']} lines (no proxy URIs detected)")
    return stats


def main():
    print(f"═══ HUNTX Output Verification ═══")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Dist:   {DIST_DIR}")

    if not OUTPUT_DIR.exists():
        print("\nOutput directory does not exist. Run the pipeline first.")
        return

    # Clean dist
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    all_outbounds: List[Dict[str, Any]] = []
    file_count = 0
    total_size = 0
    format_counts: Counter = Counter()

    print(f"\n── Validating output files ──")

    for item in sorted(OUTPUT_DIR.rglob("*")):
        if not item.is_file():
            continue

        stats = validate_file(item)
        file_count += 1
        fsize = item.stat().st_size
        total_size += fsize

        # Track format
        suffix = item.suffix.lower()
        if item.name.endswith(".decoded.json"):
            format_counts["decoded.json"] += 1
        elif item.name.endswith(".b64sub"):
            format_counts["b64sub"] += 1
        else:
            format_counts[suffix or "unknown"] += 1

        # Collect outbounds from text files
        if stats.get("outbounds"):
            all_outbounds.extend(stats["outbounds"])

        # Copy to dist
        if fsize > 0:
            shutil.copy2(item, DIST_DIR / item.name)

    print(f"\n── Summary ──")
    print(f"Files: {file_count}  Total size: {total_size / 1024:.1f} KB")
    fmts = ", ".join(f"{k}:{v}" for k, v in format_counts.most_common())
    print(f"Formats: [{fmts}]")

    if file_count > 0:
        print(f"Artifacts copied to {DIST_DIR}")

        # Copy this script
        shutil.copy2(__file__, DIST_DIR / "verify_output.py")

        # Generate V2Ray test config from vmess outbounds
        if all_outbounds:
            config_data = generate_v2ray_config(all_outbounds)
            config_path = DIST_DIR / "v2ray_test_config.json"
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)
            print(f"Generated V2Ray test config: {config_path} ({len(all_outbounds)} outbounds)")

            v2ray_exe = shutil.which("v2ray") or shutil.which("xray")
            if v2ray_exe:
                print(f"Running config check with {v2ray_exe}...")
                try:
                    subprocess.run([v2ray_exe, "test", "-c", str(config_path)], check=True)
                    print("  V2Ray config check PASSED.")
                except subprocess.CalledProcessError:
                    print("  V2Ray config check FAILED.")
            else:
                print("  v2ray/xray not in PATH — skipping runtime check.")
    else:
        print("No valid artifacts found.")


if __name__ == "__main__":
    main()
