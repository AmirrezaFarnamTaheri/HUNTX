from typing import Protocol, List, Any, Dict, runtime_checkable

@runtime_checkable
class FormatHandler(Protocol):
    @property
    def format_id(self) -> str:
        """Unique ID for this format (e.g. 'npvt', 'ovpn')."""
        ...

    def parse(self, raw_data: bytes, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse raw bytes into a list of records.
        Each record must have 'unique_hash' and 'data'.
        """
        ...

    def build(self, records: List[Dict[str, Any]]) -> bytes:
        """
        Combine multiple records into a final artifact.
        """
        ...
