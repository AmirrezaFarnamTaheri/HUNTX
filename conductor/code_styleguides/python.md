# Python Code Style Guide

## Formatting
- **Line Length**: 120 characters maximum.
- **Formatter**: Black.
- **Imports**: Standard library imports first, third-party libraries second, local application modules last. Separate sections with a blank line.

## Typing
- **Type Annotations**: All public function signatures and module interfaces must be annotated.
- **Mypy Compliance**: Run `mypy src/` without introducing new errors.

## Code Conventions
- **Docstrings**: Google-style or standard Sphinx docstrings for all non-trivial modules, classes, and public functions.
- **Exception Handling**: Catch explicit exceptions (`ValueError`, `FileNotFoundError`, `sqlite3.Error`). Never use bare `except:`.
- **Atomic File Operations**: Use atomic file write patterns (`src/huntx/utils/atomic.py`) when modifying persistent files on disk.
