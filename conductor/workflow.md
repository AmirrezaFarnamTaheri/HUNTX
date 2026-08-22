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
# Go
test -z "$(gofmt -l .)"
go test -race ./...
go vet ./...
go build ./cmd/huntx-tools
go build ./cmd/huntx-engine

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
