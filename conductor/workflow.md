# Conductor Workflow Rules

## Operational principles

1. **Evidence before change** — identify the exact source revision and the runtime path affected before making architecture/security/state claims.
2. **Test with the contract** — add or update regression coverage alongside behavioral changes; do not treat file presence as proof of integration.
3. **Use the governed runtime boundary** — operator-facing execution must go through `huntx.cli.run_service` / `create_production_orchestrator()` rather than introducing another orchestration graph.
4. **Preserve state invariants** — persistent-state changes require migration, rollback/recovery, crash/partial-failure behavior, and tests.
5. **Keep documentation truthful** — update current README/user/developer guidance when commands, configuration, state, deployment, or production reachability changes. Preserve historical ledgers as historical records.
6. **Atomic logical commits** — prefer conventional commit prefixes (`feat`, `fix`, `refactor`, `docs`, `test`, `chore`) and avoid mixing unrelated mutations.

## Required repository validation

Use the same substantive gates as PR CI:

```bash
# Workflows (fail fast on a malformed pipeline definition)
python -m pip install --require-hashes -r requirements-ci.txt -e . >/dev/null
for f in .github/workflows/*.yml; do python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" "$f"; done

# Go (build all four production binaries; the nested v2ray collector module has its own gate)
test -z "$(gofmt -l .)"
go test -race ./...
go vet ./...
go build ./cmd/huntx-tools
go build ./cmd/huntx-engine
go build ./cmd/huntx-daemon
go build ./cmd/huntx-probe
(cd src/huntx/connectors/v2ray_collector && go test ./... && go vet ./...)

# Fleet deployment manifests (Docker images + Helm chart)
docker build -f deploy/Dockerfile.daemon -t huntx-daemon:gate .
docker build -f deploy/Dockerfile.probe -t huntx-probe:gate .
helm lint deploy/helm/huntx-fleet && helm template deploy/helm/huntx-fleet >/dev/null

# Frontend assets (a drift here fails CI on the generated CSS)
npm ci
npm run build:css
git diff --exit-code -- docs/assets/css/tailwind.css
node --experimental-default-type=module --test tests/frontend_runtime.test.mjs
npx playwright test
python scripts/update_frontend.py --check

# Python
python -m pip check
python -m compileall -q -j 0 src tests scripts
python -m flake8 src/huntx tests scripts --count --statistics
python -m mypy src/huntx
python -m pytest -q -m "not perf" --strict-config --strict-markers
```

For runtime output/release verification, prefer the production Go tool used by the workflow:

```bash
huntx-tools verify-output --data-dir persist/data
huntx-tools site-data --data-dir persist/data --docs-dir docs
```

`scripts/verify_output.py` remains a compatibility/manual diagnostic helper and is intentionally not the authoritative production release gate.

## Completion rule

Do not claim a repository change is ready while its exact head has failing or unexecuted required gates. A degraded production runtime outcome is distinct from a failing source-quality gate: code quality/test failures must be fixed, not reclassified as recoverable runtime degradation.
