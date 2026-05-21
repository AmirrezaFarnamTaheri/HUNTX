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
        
        # Many malware samples are sent as ZIPs with .exe inside.
        # For now, we'll label it as ZIP and let the connector decide.
        return False, "ZIP/Archive"

    return False, "unknown"
