import os
import base64
import shutil
from pathlib import Path

# Paths
DATA_DIR = Path(os.getenv("MERGEBOT_DATA_DIR", "persist/data")).resolve()
OUTPUT_DIR = DATA_DIR / "output"
DIST_DIR = DATA_DIR / "dist"

def validate_file(path: Path) -> bool:
    print(f"Validating {path}...")
    try:
        content = path.read_bytes()
    except Exception as e:
        print(f"  ERROR: Could not read file: {e}")
        return False

    if len(content) == 0:
        print("  WARNING: File is empty.")
        return False

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        print("  INFO: Binary file (likely zip or opaque bundle).")
        return True # Treat as valid binary

    is_base64 = False
    decoded_text = None

    clean_text = text.strip()
    if " " not in clean_text and len(clean_text) > 0:
        try:
            decoded = base64.b64decode(clean_text).decode("utf-8")
            decoded_text = decoded
            is_base64 = True
        except Exception:
            pass

    target_text = decoded_text if is_base64 else text

    # Basic proxy check
    proxies = ["vmess://", "vless://", "trojan://", "ss://", "ssr://"]
    found_proxy = any(p in target_text for p in proxies)

    if found_proxy:
        print("  SUCCESS: Found proxy configuration.")
        if is_base64:
             print("  INFO: Content was Base64 encoded.")
    else:
        # Might be conf lines or something else
        lines = target_text.splitlines()
        print(f"  INFO: Text file with {len(lines)} lines. No obvious proxy scheme found.")

    return True

def main():
    print(f"Checking output directory: {OUTPUT_DIR}")

    if not OUTPUT_DIR.exists():
        print("Output directory does not exist.")
        return

    # Clean dist
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    found_any = False
    for item in OUTPUT_DIR.rglob("*"):
        if item.is_file():
            if validate_file(item):
                # Copy to dist with a flattened name for easy artifact download
                # e.g. route_name/route.fmt -> route.fmt
                dest_name = item.name
                shutil.copy2(item, DIST_DIR / dest_name)
                found_any = True

    if found_any:
        print(f"Artifacts copied to {DIST_DIR}")
        # Copy this script too so user can use it
        shutil.copy2(__file__, DIST_DIR / "verify_output.py")
    else:
        print("No valid artifacts found.")

if __name__ == "__main__":
    main()
