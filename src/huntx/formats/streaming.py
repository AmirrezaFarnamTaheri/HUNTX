import base64
import hashlib
from typing import AsyncIterator, Dict, Any, List, Optional


class StreamingChunkParser:
    """
    Zero-copy streaming parser for multi-gigabyte subscription bundles.
    Processes stream chunks in 64KB blocks without accumulating full payloads in memory.
    """

    def __init__(self, chunk_size: int = 65536):
        self.chunk_size = chunk_size

    def _hash_record(self, raw_line: str) -> str:
        return hashlib.sha256(raw_line.strip().encode("utf-8")).hexdigest()[:16]

    def _extract_protocol(self, uri: str) -> str:
        if "://" in uri:
            return uri.split("://", 1)[0].lower()
        return "unknown"

    def parse_line(self, line: str, source_info: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            return None
        proto = self._extract_protocol(cleaned)
        return {
            "unique_hash": self._hash_record(cleaned),
            "data": cleaned.encode("utf-8"),
            "raw_uri": cleaned,
            "protocol": proto,
            "source_info": source_info or {},
        }

    async def parse_stream(
        self, stream: AsyncIterator[bytes], source_info: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Asynchronously yields parsed proxy record dicts from a chunked bytes stream.
        """
        buffer = ""
        b64_remainder = b""

        async for chunk in stream:
            if not chunk:
                continue

            # Try to decode chunk directly or append to base64 remainder
            try:
                text_chunk = (b64_remainder + chunk).decode("utf-8")
                b64_remainder = b""
            except UnicodeDecodeError:
                # If base64 encoded stream, attempt base64 chunk decoding
                combined = b64_remainder + chunk
                # Align to 4-byte base64 boundary
                remainder_len = len(combined) % 4
                if remainder_len != 0:
                    valid_part = combined[:-remainder_len]
                    b64_remainder = combined[-remainder_len:]
                else:
                    valid_part = combined
                    b64_remainder = b""

                try:
                    decoded = base64.b64decode(valid_part, validate=False)
                    text_chunk = decoded.decode("utf-8", errors="ignore")
                except Exception:
                    text_chunk = chunk.decode("utf-8", errors="ignore")

            buffer += text_chunk
            lines = buffer.splitlines(keepends=True)

            # Process completed lines, keep incomplete trailing line in buffer
            if lines:
                if not buffer.endswith(("\r", "\n")):
                    buffer = lines.pop()
                else:
                    buffer = ""

                for line in lines:
                    record = self.parse_line(line, source_info)
                    if record:
                        yield record

        # Process any remaining text in buffer
        if buffer:
            for line in buffer.splitlines():
                record = self.parse_line(line, source_info)
                if record:
                    yield record

    def parse_bytes(self, raw_bytes: bytes, source_info: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Synchronous fallback helper to parse raw byte arrays into records.
        """
        text = ""
        try:
            # Check if entire payload is base64 encoded
            decoded = base64.b64decode(raw_bytes.strip(), validate=True)
            text = decoded.decode("utf-8", errors="ignore")
        except Exception:
            text = raw_bytes.decode("utf-8", errors="ignore")

        records = []
        for line in text.splitlines():
            rec = self.parse_line(line, source_info)
            if rec:
                records.append(rec)
        return records
