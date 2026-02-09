import os
import base64
import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any

# Paths
DATA_DIR = Path(os.getenv("MERGEBOT_DATA_DIR", "persist/data")).resolve()
OUTPUT_DIR = DATA_DIR / "output"
DIST_DIR = DATA_DIR / "dist"

def decode_base64_safe(data: str) -> str:
    # Add padding if needed
    missing_padding = len(data) % 4
    if missing_padding:
        data += '=' * (4 - missing_padding)
    return base64.b64decode(data).decode("utf-8", errors="ignore")

def parse_vmess(link: str) -> Dict[str, Any]:
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
            # Simplified; real conversion needs more fields (ws settings, etc)
            # but this is enough for basic config validity check
        },
        "tag": vdata.get("ps", "proxy")
    }

def validate_file(path: Path) -> List[Dict[str, Any]]:
    print(f"Validating {path}...")
    try:
        content = path.read_bytes()
    except Exception as e:
        print(f"  ERROR: Could not read file: {e}")
        return []

    if len(content) == 0:
        print("  WARNING: File is empty.")
        return []

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        print("  INFO: Binary file (likely zip or opaque bundle).")
        return []

    # Handle Base64 encoded file content
    clean_text = text.strip()
    if " " not in clean_text and len(clean_text) > 0:
        try:
            decoded = decode_base64_safe(clean_text)
            text = decoded
            print("  INFO: Decoded Base64 file content.")
        except Exception:
            pass

    outbounds = []
    lines = text.splitlines()
    vmess_count = 0

    for line in lines:
        line = line.strip()
        if line.startswith("vmess://"):
            vdata = parse_vmess(line)
            if vdata:
                vmess_count += 1
                outbounds.append(convert_vmess_to_outbound(vdata))

    if vmess_count > 0:
        print(f"  SUCCESS: Found {vmess_count} valid VMess links.")
    else:
        print(f"  INFO: Text file with {len(lines)} lines. No VMess links parsed.")

    return outbounds

def main():
    print(f"Checking output directory: {OUTPUT_DIR}")

    if not OUTPUT_DIR.exists():
        print("Output directory does not exist.")
        return

    # Clean dist
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    all_outbounds = []
    found_any = False

    for item in OUTPUT_DIR.rglob("*"):
        if item.is_file():
            # Validate and collect outbounds
            file_outbounds = validate_file(item)
            if file_outbounds:
                all_outbounds.extend(file_outbounds)

            # Copy to dist if it looks valid (simple size check or just copy all outputs)
            if item.stat().st_size > 0:
                shutil.copy2(item, DIST_DIR / item.name)
                found_any = True

    if found_any:
        print(f"Artifacts copied to {DIST_DIR}")

        # Copy this script
        shutil.copy2(__file__, DIST_DIR / "verify_output.py")

        # Generate Test Config
        if all_outbounds:
            config_data = generate_v2ray_config(all_outbounds)
            config_path = DIST_DIR / "v2ray_test_config.json"
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)
            print(f"Generated V2Ray test config at: {config_path}")

            # Try running V2Ray test
            v2ray_exe = shutil.which("v2ray") or shutil.which("xray")
            if v2ray_exe:
                print(f"Found binary: {v2ray_exe}. Running config check...")
                try:
                    subprocess.run([v2ray_exe, "test", "-c", str(config_path)], check=True)
                    print("  SUCCESS: V2Ray config check passed.")
                except subprocess.CalledProcessError:
                    print("  FAILURE: V2Ray config check failed.")
            else:
                print("  INFO: v2ray/xray binary not found in PATH. Skipping runtime check.")

    else:
        print("No valid artifacts found.")

if __name__ == "__main__":
    main()
