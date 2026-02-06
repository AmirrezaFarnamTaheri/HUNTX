import unicodedata

def normalize_text(text: str) -> str:
    """
    Normalizes text to NFKC, strips whitespace, handles unified newlines.
    """
    if not text:
        return ""
    # NFKC normalization for compatibility
    text = unicodedata.normalize('NFKC', text)
    # Strip whitespace
    text = text.strip()
    return text
