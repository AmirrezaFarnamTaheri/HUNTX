from pathlib import Path


def test_production_workflow_uses_verified_atomic_generations():
    workflow = Path(".github/workflows/huntx.yml").read_text()
    assert "pull_request:" not in workflow
    assert "timeout-minutes: 115" in workflow
    assert 'HUNTX_RUN_TIMEOUT: "5400"' in workflow
    assert 'HUNTX_ALLOW_PARTIAL_SUCCESS: "true"' in workflow
    assert 'HUNTX_ALLOW_PARTIAL_EXPORT: "true"' in workflow
    assert 'HUNTX_RUN_SUMMARY_PATH: "persist/data/logs/run-summary.json"' in workflow
    assert "timeout --signal=TERM --kill-after=60s 105m" in workflow
    assert "scripts/checkpoint_runtime_state.py" in workflow
    assert "scripts/report_runtime_health.py" in workflow
    assert "huntx-tools runtime-generation" in workflow
    assert "huntx-tools verify-output" in workflow
    assert "huntx-tools site-data" in workflow
    assert "id-token: write" in workflow
    assert workflow.count("actions/setup-go@4a3601121dd01d1626a1e23e37211e3254c1c06c") == 4
    assert "needs: validate" in workflow
    assert "restore-verified-state" in workflow
    assert "ingest-build-package" in workflow
    assert "persist-immutable-state" in workflow

    payload_upload = workflow.index("aws s3 sync checkpoint-package/payload")
    manifest_upload = workflow.index("aws s3 cp checkpoint-package/generation-manifest.json")
    pointer_upload = workflow.index("aws s3 cp checkpoint-package/next-current.json")
    assert payload_upload < manifest_upload < pointer_upload


def test_production_workflow_exposes_structured_degraded_success():
    workflow = Path(".github/workflows/huntx.yml").read_text()
    assert "Publish structured runtime diagnostics" in workflow
    assert "runtime_disposition:" in workflow
    assert "Enforce only truly fatal runtime outcomes" in workflow
    assert 'if [[ "$disposition" == "degraded" ]]' in workflow
    assert "124|137|143" in workflow
    assert "Upload logs and structured diagnostics" in workflow
    assert "Describe runtime context" in workflow
    assert "Summarize quality gate" in workflow
    assert "Summarize immutable persistence" in workflow


def test_production_workflow_packages_and_deploys_only_verified_output():
    workflow = Path(".github/workflows/huntx.yml").read_text()
    assert "package_ready: ${{ steps.package.outputs.ready }}" in workflow
    assert "if: steps.package.outputs.ready == 'true'" in workflow
    assert "needs.run.outputs.package_ready == 'true'" in workflow
    assert "No packageable output" in workflow
    assert "Output verification degraded" in workflow


def test_pull_request_workflow_has_no_oidc_permission():
    workflow = Path(".github/workflows/pr-validation.yml").read_text()
    assert "pull_request:" in workflow
    assert "id-token: write" not in workflow
    assert "actions/setup-go@4a3601121dd01d1626a1e23e37211e3254c1c06c" in workflow


def test_go_release_plane_is_present():
    assert Path("cmd/huntx-tools/main.go").exists()
    assert Path("internal/runtimegen/runtimegen.go").exists()
    assert Path("internal/releasemanifest/releasemanifest.go").exists()
    assert Path("internal/outputverify/outputverify.go").exists()
    assert Path("internal/sitegen/sitegen.go").exists()
