import os
import shutil
import base64
import json
import subprocess
from pathlib import Path

def main():
    data_dir = Path(os.getenv("MERGEBOT_DATA_DIR", "persist/data")).resolve()
    artifacts_dir = data_dir / "artifacts"
    dist_dir = data_dir / "dist"

    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True)

    print(f"Scanning artifacts in {artifacts_dir}...")

    if not artifacts_dir.exists():
        print("Artifacts directory not found.")
        return

    for route_dir in artifacts_dir.iterdir():
        if not route_dir.is_dir():
            continue

        route_name = route_dir.name
        print(f"Processing route: {route_name}")

        for artifact_file in route_dir.glob("*.bin"):
            print(f"  Checking {artifact_file.name}...")

            try:
                content = artifact_file.read_bytes()

                # Sniff format
                fmt = "unknown"
                ext = ".bin"
                decoded_content = None

                # Check 1: Plain text / Conf lines
                try:
                    text = content.decode("utf-8")
                    if "client" in text and "dev tun" in text:
                        fmt = "ovpn"
                        ext = ".ovpn"
                    elif text.startswith("vmess://") or text.startswith("vless://") or text.startswith("ss://") or text.startswith("trojan://"):
                         fmt = "npvt_plain"
                         ext = ".txt"
                    else:
                        # Check Base64
                        try:
                            decoded = base64.b64decode(text).decode("utf-8")
                            if any(decoded.startswith(p) for p in ["vmess://", "vless://", "ss://", "trojan://"]):
                                fmt = "npvt"
                                ext = ".txt"
                                decoded_content = decoded
                            else:
                                # Maybe just lines of configs
                                fmt = "conf_lines"
                                ext = ".txt"
                        except Exception:
                            # Not base64
                            fmt = "text"
                            ext = ".txt"
                except Exception:
                    # Binary
                    if content.startswith(b"PK"):
                        fmt = "bundle"
                        ext = ".zip"

                print(f"    Detected format: {fmt}")

                # Copy to dist
                dest_name = f"{route_name}_{fmt}_{artifact_file.stem[:8]}{ext}"
                shutil.copy(artifact_file, dist_dir / dest_name)

                # Verification / Testing
                if fmt == "npvt" and decoded_content:
                    verify_v2ray(decoded_content)

            except Exception as e:
                print(f"    Error processing {artifact_file.name}: {e}")

def verify_v2ray(links_text):
    # Basic verification of link structure
    links = links_text.strip().splitlines()
    valid_count = 0
    for link in links:
        link = link.strip()
        if not link: continue
        if link.startswith("vmess://") or link.startswith("vless://") or link.startswith("trojan://") or link.startswith("ss://"):
             valid_count += 1
        else:
             print(f"    WARNING: Invalid link format: {link[:20]}...")
    print(f"    Verified {valid_count} valid links.")

if __name__ == "__main__":
    main()
