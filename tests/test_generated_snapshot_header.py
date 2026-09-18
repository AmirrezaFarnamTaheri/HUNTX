"""Regression tests for the generated snapshot's proxies.txt header.

`git diff --cached --check` rejects trailing whitespace in the committed
snapshot, and an empty source timestamp used to leave a dangling em dash
separator behind ("# huntx proxy list "), which failed publication. The
header must stay clean whatever timestamp it is handed.
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_assembler() -> ModuleType:
    path = REPO_ROOT / "scripts" / "assemble_generated_snapshot.py"
    spec = importlib.util.spec_from_file_location("assemble_generated_snapshot_header", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ASSEMBLER = _load_assembler()


class TestCleanHeaderWhateverTheTimestamp(unittest.TestCase):
    def _proxies_txt(self, source_created_at: str) -> bytes:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint = root / "checkpoint" / "data"
            outputs = checkpoint / "outputs"
            outputs.mkdir(parents=True)
            (outputs / "current.txt").write_text("vless://a.example:443?encryption=none\n")
            dist = root / "dist"
            logs = root / "logs"
            dist.mkdir()
            logs.mkdir()
            (dist / "catalog.json").write_text("{}\n")

            ASSEMBLER.assemble_snapshot(
                checkpoint_root=checkpoint,
                dist_root=dist,
                logs_root=logs,
                destination=root / "snapshot",
                run_id="123",
                run_attempt="1",
                head_sha="abc123",
                head_branch="main",
                source_created_at=source_created_at,
            )
            # write_text translates to CRLF on Windows; CI commits LF, so
            # normalize before asserting on line content.
            return (root / "snapshot" / "outputs_dev" / "proxies.txt").read_bytes().replace(
                b"\r\n", b"\n"
            )

    def test_empty_timestamp_drops_the_separator(self):
        rendered = self._proxies_txt("")
        self.assertEqual(rendered.split(b"\n")[0], b"# huntx proxy list")

    def test_no_line_carries_trailing_whitespace_without_a_timestamp(self):
        rendered = self._proxies_txt("")
        offenders = [i + 1 for i, line in enumerate(rendered.split(b"\n")) if line != line.rstrip()]
        self.assertEqual(offenders, [], f"trailing whitespace on lines {offenders}")

    def test_present_timestamp_is_rendered_and_clean(self):
        rendered = self._proxies_txt("2026-07-30T17:24:27Z")
        expected = "# huntx proxy list — 2026-07-30 17:24:27 UTC".encode("utf-8")
        self.assertEqual(rendered.split(b"\n")[0], expected)
        offenders = [i + 1 for i, line in enumerate(rendered.split(b"\n")) if line != line.rstrip()]
        self.assertEqual(offenders, [], f"trailing whitespace on lines {offenders}")


if __name__ == "__main__":
    unittest.main()
