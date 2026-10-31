"""Independent ground truth is required for a confusion-matrix claim."""
from __future__ import annotations

import pytest
from scripts.audit_pipeline_evidence import score_labeled, audit_artifacts, AuditError, STAGES


def _fixture():
    summary = {
        "schema_version": 1,
        "summary": {
            "sources_checked": 3,
            "messages_scanned": 0,
            "lifo_windows_completed": 0,
            "lifo_residue": {"remaining": 6, "retry_wait": 6},
            "http_nodes_observed": 15,
            "release_eligible": False,
            "status": "partial",
            "transform": {"completed": True},
            "total_artifacts": 3,
        },
    }
    health = {
        "schema_version": 1,
        "counts": {
            "configured_sources": 5,
            "enabled": 4,
            "disabled": 1,
            "http_retrieved": 2,
            "http_source_failures": 1,
            "http_infrastructure_errors": 0,
            "http_not_observed": 0,
            "telegram_retrying": 1,
            "telegram_observed": 0,
            "telegram_quarantined": 0,
            "telegram_not_observed": 0,
        },
        "sources": [
            {"enabled": True, "type": "http_subscription", "status": "retrieved", "id": "http-a"},
            {"enabled": True, "type": "http_subscription", "status": "retrieved", "id": "http-b"},
            {"enabled": True, "type": "http_subscription", "status": "source_failure", "id": "http-c"},
            {"enabled": True, "type": "telegram_user", "status": "retrying", "id": "telegram-a"},
            {"enabled": False, "type": "telegram_user", "status": "disabled", "id": "telegram-b"},
        ],
    }
    inventory = {
        "schema_version": 1,
        "counts": {
            "records_scanned": 12,
            "invalid_records": 1,
            "distinct_endpoint_ids": 5,
            "network_endpoints": 5,
            "duplicate_endpoint_observations": 6,
            "unresolved_geo": 4,
            "unattributed_asn": 5,
        },
        "status": "complete",
        "scope": "public_endpoint_metadata_not_proxy_authentication",
    }
    network = {
        "schema_version": 1,
        "scope": "dns_tcp_standard_tls_only",
        "counts": {"candidates": 5, "selected": 3, "tested": 3},
        "layers": {
            "tcp": {"connected": 1, "timeout": 2},
            "proxy_protocol": {"unverified": 3},
        },
    }
    return summary, health, inventory, network


def test_unlabeled_evidence_never_manufactures_tp_tn_fp_fn():
    result = audit_artifacts(*_fixture())
    assert result["confusion_matrix_status"] == "no_independent_labels"
    assert result["stages"]["proxy_authentication"]["verdict"] == "unknown"
    assert result["stages"]["telegram_ingestion"]["verdict"] == "degraded"
    assert result["stages"]["http_ingestion"]["observed"]["retrieved"] == 2
    assert result["stages"]["semantic_deduplication"]["verdict"] == "unknown"


def test_confusion_matrix_counts_all_four_outcomes_and_abstention():
    labels = [
        {"stage": "http_ingestion", "sample_id": "a", "predicted": True, "truth": True, "oracle": "independent_fixture"},
        {"stage": "http_ingestion", "sample_id": "b", "predicted": False, "truth": False, "oracle": "independent_fixture"},
        {"stage": "http_ingestion", "sample_id": "c", "predicted": True, "truth": False, "oracle": "independent_fixture"},
        {"stage": "http_ingestion", "sample_id": "d", "predicted": False, "truth": True, "oracle": "independent_fixture"},
        {"stage": "http_ingestion", "sample_id": "e", "predicted": None, "truth": True, "oracle": "independent_fixture"},
    ]
    result = score_labeled(labels)["http_ingestion"]
    assert (result["tp"], result["tn"], result["fp"], result["fn"], result["abstain"]) == (1, 1, 1, 1, 1)
    assert result["precision"] == result["recall"] == result["specificity"] == 0.5
    assert result["support"] == 4
    assert result["ground_truth_count"] == 5


def test_single_class_has_undefined_metrics_instead_of_zero():
    data = score_labeled([{"stage": "http_ingestion", "sample_id": "a", "predicted": False,
                          "truth": False, "oracle": "independent_fixture"}])["http_ingestion"]
    assert data["recall"] is None
    assert data["precision"] is None
    assert data["specificity"] == 1.0
    assert data["fpr"] == 0.0


@pytest.mark.parametrize("bad", [
    {"stage": "http_ingestion", "sample_id": "a", "predicted": True, "truth": True},
    {"stage": "http_ingestion", "sample_id": "a", "predicted": 1, "truth": False, "oracle": "independent_fixture"},
    {"stage": "http_ingestion", "sample_id": "a", "predicted": True, "truth": "yes", "oracle": "independent_fixture"},
    {"stage": "unknown", "sample_id": "a", "predicted": True, "truth": True, "oracle": "independent_fixture"},
])
def test_rejects_invalid_or_unattributed_ground_truth(bad):
    with pytest.raises(AuditError):
        score_labeled([bad])


def test_duplicate_labeled_sample_cannot_inflate_quality():
    row = {"stage": "http_ingestion", "sample_id": "a", "predicted": True,
           "truth": True, "oracle": "independent_fixture"}
    with pytest.raises(AuditError, match="duplicate"):
        score_labeled([row, row])


def test_cross_artifact_count_mismatch_must_be_observable():
    summary, health, inventory, network = _fixture()
    health["counts"]["enabled"] = 9
    with pytest.raises(AuditError, match="enabled sources"):
        audit_artifacts(summary, health, inventory, network)


def test_endpoint_identity_duplicates_are_not_semantic_proxy_duplicates():
    result = audit_artifacts(*_fixture())
    assert result["stages"]["endpoint_identity"]["observed"]["repeated_endpoint_observations"] == 6
    assert result["stages"]["semantic_deduplication"]["verdict"] == "unknown"


def test_all_stages_declared_for_every_audit():
    report = audit_artifacts(*_fixture())
    assert set(report["stages"]) == set(STAGES)
