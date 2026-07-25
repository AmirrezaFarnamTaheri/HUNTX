# Conductor Workflow Rules

## Operational Principles
1. **Spec-Driven Development**: Every track feature or bug fix must have a specification in `conductor/tracks/` with `spec.md` and `plan.md`.
2. **Quality-Gated Implementation**:
   - Write tests first or alongside code changes.
   - Run static analysis (`flake8`, `mypy`) and pytest verification before completing any task.
3. **Atomic Commits**:
   - Scope git commits to single logical changes.
   - Use conventional commit formats (`feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `conductor`).

## Verification Commands
- **Unit & Integration Tests**: `pytest`
- **Linting**: `flake8 src/ tests/`
- **Type Checking**: `mypy src/`
- **Full Pipeline Audit**: `python scripts/verify_output.py`
