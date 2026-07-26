import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Common executable magic numbers
# ZIP (includes APK, JAR)
_ZIP_MAGIC = b"PK\x03\x04"
# Windows Executable
_EXE_MAGIC = b"MZ"
# Linux Executable
_ELF_MAGIC = b"\x7fELF"
# Mach-O (macOS)
_MACHO_MAGIC_32 = b"\xfe\xed\xfa\xce"
_MACHO_MAGIC_64 = b"\xfe\xed\xfa\xcf"
_MACHO_MAGIC_FAT = b"\xca\xfe\xba\xbe"


def is_executable(data: bytes) -> Tuple[bool, str]:
    """
    Perform deep magic-byte inspection to detect executables.
    Returns (is_exec, type_description).
    """
    if not data:
        return False, "empty"

    header = data[:4]

    if header.startswith(_EXE_MAGIC):
        return True, "Windows Executable (PE)"

    if header.startswith(_ELF_MAGIC):
        return True, "Linux Executable (ELF)"

    if header == _MACHO_MAGIC_32 or header == _MACHO_MAGIC_64 or header == _MACHO_MAGIC_FAT:
        # Note: 0xcafebabe is also Java class file magic, but in this context
        # (Telegram files) it's mostly Mach-O or something we want to skip anyway.
        return True, "macOS Executable (Mach-O/Fat)"

    if header == _ZIP_MAGIC:
        # APKs are ZIPs. While we might want some ZIPs, the primary use case for HuntX
        # is text/config files. Opaque bundles are handled separately.
        # Check for APK signature if needed, but blocking ZIPs in the scraper
        # is generally safe as legitimate configs are rarely sent as raw ZIPs
        # (they are either text or caught by specific handlers).

        # Look for "AndroidManifest.xml" which is a strong indicator of an APK
        # (Usually found in the first few KB of the ZIP central directory or local headers)
        if b"AndroidManifest.xml" in data[:4096]:
            return True, "Android Package (APK)"

        import zipfile
        import io

        def scan_zip_recursive(zip_bytes: bytes, current_depth: int, state: dict) -> Tuple[bool, str]:
            if current_depth > 3:
                return True, "ZIP recursion depth exceeded (potential evasion/zip bomb)"

            try:
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                    infos = zf.infolist()
                    if len(infos) > 500:
                        return True, f"ZIP contains too many files ({len(infos)}), potential zip bomb"

                    for info in infos:
                        if info.is_dir():
                            continue

                        fname = info.filename
                        normalized_name = fname.replace("\\", "/")
                        parts = normalized_name.split("/")

                        # Zip Slip prevention: check path traversal or absolute paths
                        if ".." in parts or normalized_name.startswith("/") or ":" in normalized_name:
                            return True, f"ZIP contains potential path traversal exploit (Zip Slip): {fname}"

                        # Detect APK manifest filename
                        if fname == "AndroidManifest.xml" or fname.endswith("/AndroidManifest.xml"):
                            return True, f"ZIP contains APK ({fname})"

                        # Track total decompressed bytes to prevent Zip Bomb
                        state["decompressed_bytes"] += info.file_size
                        if state["decompressed_bytes"] > 50 * 1024 * 1024:
                            return True, "ZIP decompress limit exceeded (potential zip bomb)"

                        try:
                            with zf.open(info) as member:
                                member_header = member.read(4)
                                if member_header.startswith(_EXE_MAGIC):
                                    return True, f"ZIP contains Windows Executable ({fname})"
                                if member_header.startswith(_ELF_MAGIC):
                                    return True, f"ZIP contains Linux Executable ({fname})"
                                if member_header in (_MACHO_MAGIC_32, _MACHO_MAGIC_64, _MACHO_MAGIC_FAT):
                                    return True, f"ZIP contains macOS Executable ({fname})"

                                # Recursive scanning of nested archives
                                if member_header == _ZIP_MAGIC or fname.lower().endswith((".zip", ".apk", ".jar")):
                                    member_bytes = member_header + member.read()
                                    is_nest_exec, nest_desc = scan_zip_recursive(member_bytes, current_depth + 1, state)
                                    if is_nest_exec:
                                        return True, f"Nested ZIP error in {fname}: {nest_desc}"
                        except Exception as e:
                            logger.warning(f"Error checking zip member {fname}: {e}")
            except zipfile.BadZipFile:
                pass
            except Exception as e:
                logger.warning(f"Unexpected error parsing ZIP in recursive scanner: {e}")
                return True, f"Corrupted or malicious ZIP structure: {e}"

            return False, ""

        state = {"decompressed_bytes": 0}
        is_malicious, desc = scan_zip_recursive(data, 1, state)
        if is_malicious:
            return True, desc

        return False, "ZIP/Archive"

    return False, "unknown"
