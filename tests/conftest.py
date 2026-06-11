import sys
from pathlib import Path


# Ensure `import huntx` works when running tests without editable install.
_here = Path(__file__).resolve()
_project_root = _here.parents[1]  # .../HUNTX
_src = _project_root / "src"

if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

