import base64
import codecs
import hashlib
from typing import AsyncIterator, Dict, Any, List, Optional


_BASE64_ALPHABET = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")


class StreamingChunkParser:
    """
    Streaming parser for large subscription bundles.
    Processes raw UTF-8 or Base64-encoded streams without accumulating the full payload.
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

    @staticmethod
    def _compact_base64(data: bytes) -> bytes:
        return b"".join(data.split())

    def _detect_stream_mode(self, data: bytes) -> Optional[str]:
        """Return raw/base64 once the buffered prefix contains enough evidence."""
        compact = self._compact_base64(data)
        if not compact:
            return None
        if any(byte not in _BASE64_ALPHABET for byte in compact):
            return "raw"

        sample_len = len(compact) - (len(compact) % 4)
        if sample_len >= 8:
            try:
                decoded = base64.b64decode(compact[:sample_len], validate=True)
                sample = decoded.decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                sample = ""
            if "://" in sample or "\n" in sample or "\r" in sample:
                return "base64"

        detection_limit = max(64, min(self.chunk_size, 4096))
        if len(data) >= detection_limit:
            return "raw"
        return None

    async def parse_stream(
        self, stream: AsyncIterator[bytes], source_info: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """Yield parsed records from raw UTF-8 or Base64-encoded byte chunks."""
        mode: Optional[str] = None
        pending = bytearray()
        b64_remainder = b""
        text_buffer = ""
        decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")

        def feed_text(text_chunk: str) -> List[Dict[str, Any]]:
            nonlocal text_buffer
            if not text_chunk:
                return []
            text_buffer += text_chunk
            lines = text_buffer.splitlines(keepends=True)
            if lines and not text_buffer.endswith(("\r", "\n")):
                text_buffer = lines.pop()
            else:
                text_buffer = ""

            records: List[Dict[str, Any]] = []
            for line in lines:
                parsed_record = self.parse_line(line, source_info)
                if parsed_record:
                    records.append(parsed_record)
            return records

        def decode_payload(data: bytes) -> bytes:
            nonlocal b64_remainder
            if mode == "raw":
                return data

            compact = self._compact_base64(data)
            combined = b64_remainder + compact
            complete_len = len(combined) - (len(combined) % 4)
            if complete_len == 0:
                b64_remainder = combined
                return b""
            encoded = combined[:complete_len]
            b64_remainder = combined[complete_len:]
            try:
                return base64.b64decode(encoded, validate=True)
            except ValueError:
                return b""

        async for chunk in stream:
            if not chunk:
                continue

            if mode is None:
                pending.extend(chunk)
                mode = self._detect_stream_mode(bytes(pending))
                if mode is None:
                    continue
                chunk = bytes(pending)
                pending.clear()

            decoded_bytes = decode_payload(chunk)
            for parsed_record in feed_text(decoder.decode(decoded_bytes, final=False)):
                yield parsed_record

        if mode is None:
            mode = "raw"
            decoded_bytes = bytes(pending)
        else:
            decoded_bytes = b""

        if mode == "base64" and b64_remainder:
            padded = b64_remainder + (b"=" * (-len(b64_remainder) % 4))
            try:
                decoded_bytes += base64.b64decode(padded, validate=True)
            except ValueError:
                pass
            b64_remainder = b""

        final_text = decoder.decode(decoded_bytes, final=True)
        for parsed_record in feed_text(final_text):
            yield parsed_record

        if text_buffer:
            for line in text_buffer.splitlines():
                remaining_record = self.parse_line(line, source_info)
                if remaining_record:
                    yield remaining_record

    def parse_bytes(self, raw_bytes: bytes, source_info: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Parse a complete raw or Base64-encoded byte payload into records."""
        try:
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
