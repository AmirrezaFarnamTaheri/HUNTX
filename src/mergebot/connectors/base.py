from typing import Protocol, Iterator, Dict, Any, Optional

class SourceItem(Protocol):
    external_id: str
    data: bytes
    metadata: Dict[str, Any] # must contain 'filename' if possible

class SourceConnector(Protocol):
    def list_new(self, state: Optional[Dict[str, Any]]) -> Iterator[SourceItem]:
        """
        Yields new items since the last state.
        Should handle its own state tracking internally or return it?
        Usually connector keeps track of 'last_offset' and uses it in next call.
        """
        ...

    def get_state(self) -> Dict[str, Any]:
        """Return current state (e.g. last_offset) to be saved."""
        ...
