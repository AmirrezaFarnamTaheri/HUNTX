# Emergent Lessons Learned & ELF Intelligence

## 1. Post-Stash & Multi-Language Conflict Hygiene
- **Symptom**: Syntax errors in Python or missing import errors in Go (`main.go:16:1: missing import path`) following server restarts or stash operations.
- **Root Cause**: Server restarts or background Git operations can leave unmerged Git conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) inside source code files.
- **Remediation**: Run a text search audit across all source directories prior to execution:
  `rg "<<<<<<<|>>>>>>>|=======" src/ cmd/ tests/`

## 2. Python Subclass Liskov Substitution (LSP) Invariance
- **Symptom**: `mypy` error: `Signature of "process_pending" incompatible with supertype`.
- **Root Cause**: Subclasses like `OptimizedTransformPipeline` override `process_pending(self, *, deadline: float | None = ..., max_batches: int | None = ...)` while parent `TransformPipeline` defined `def process_pending(self) -> None`.
- **Remediation**: Parent class method definitions must include optional keyword arguments (`*, deadline: Optional[float] = None, max_batches: Optional[int] = None`) to maintain LSP compatibility across the hierarchy.

## 3. Windows Pytest Basetemp Permission Isolation
- **Symptom**: `PermissionError: [WinError 5] Access is denied: ...\pytest-current` on Windows during bulk test suite execution.
- **Root Cause**: File handle locks from concurrent background processes on the default OS temporary directory.
- **Remediation**: Pass a local isolated build directory `--basetemp=temp_pytest_dir` when executing high-throughput test runs in background shell sessions on Windows.
