"""Pipeline runtime hooks.

The Telegram connector records acknowledgement candidates during ingestion.
The durable watermark is committed only after IngestionPipeline has persisted
source state successfully.
"""

from .ingest import IngestionPipeline

_original_run = IngestionPipeline.run


async def _run_with_ack_commit(self, source_id, connector, *args, **kwargs):
    result = await _original_run(self, source_id, connector, *args, **kwargs)
    commit = getattr(connector, "commit_acknowledgement", None)
    if commit is not None:
        commit()
    return result


IngestionPipeline.run = _run_with_ack_commit

__all__ = ["IngestionPipeline"]
