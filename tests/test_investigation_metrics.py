from types import SimpleNamespace

from huntx.core.optimized_orchestrator import OptimizedHardenedOrchestrator


def test_investigation_metrics_reset_and_shape():
    orchestrator = object.__new__(OptimizedHardenedOrchestrator)
    orchestrator._sources_checked = {"old"}
    orchestrator._messages_scanned = 9
    orchestrator._messages_new = 4
    orchestrator._cursor_updates = 3

    orchestrator._reset_investigation_metrics()

    assert orchestrator._investigation_metrics() == {
        "sources_checked": 0,
        "messages_scanned": 0,
        "messages_new": 0,
        "cursor_updates": 0,
    }


def test_investigation_metrics_count_unique_sources():
    orchestrator = object.__new__(OptimizedHardenedOrchestrator)
    orchestrator._sources_checked = {"a", "a", "b"}
    orchestrator._messages_scanned = 12
    orchestrator._messages_new = 5
    orchestrator._cursor_updates = 2

    assert orchestrator._investigation_metrics() == {
        "sources_checked": 2,
        "messages_scanned": 12,
        "messages_new": 5,
        "cursor_updates": 2,
    }


def test_source_set_semantics_do_not_double_count_window_pages():
    orchestrator = object.__new__(OptimizedHardenedOrchestrator)
    orchestrator._reset_investigation_metrics()
    page_sources = [
        SimpleNamespace(id="channel-a"),
        SimpleNamespace(id="channel-a"),
        SimpleNamespace(id="channel-b"),
    ]
    for source in page_sources:
        orchestrator._sources_checked.add(str(source.id))

    assert orchestrator._investigation_metrics()["sources_checked"] == 2
