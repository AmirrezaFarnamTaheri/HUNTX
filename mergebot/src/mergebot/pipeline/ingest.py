import logging
from typing import Dict, Any
from ..connectors.base import SourceConnector
from ..store.raw_store import RawStore
from ..state.repo import StateRepo

logger = logging.getLogger(__name__)

class IngestionPipeline:
    def __init__(self, raw_store: RawStore, state_repo: StateRepo):
        self.raw_store = raw_store
        self.state_repo = state_repo

    def run(self, source_id: str, connector: SourceConnector):
        state = self.state_repo.get_source_state(source_id)

        count = 0
        for item in connector.list_new(state):
            if self.state_repo.has_seen_file(source_id, item.external_id):
                continue

            raw_hash = self.raw_store.save(item.data)

            filename = item.metadata.get("filename", "unknown")

            self.state_repo.record_file(
                source_id=source_id,
                external_id=item.external_id,
                raw_hash=raw_hash,
                file_size=len(item.data),
                filename=filename,
                status="pending"
            )
            count += 1

        new_state = connector.get_state()
        self.state_repo.update_source_state(source_id, new_state, source_type="telegram")

        if count > 0:
            logger.info(f"Ingested {count} new files from {source_id}")
