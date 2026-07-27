import json
import tempfile
import unittest
from pathlib import Path

from scripts.runtime_generation import (
    build_manifest,
    build_pointer,
    validate_pointer,
    verify_manifest,
)


class RuntimeGenerationTests(unittest.TestCase):
    def test_manifest_roundtrip_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "data").mkdir()
            (root / "state.db").write_bytes(b"sqlite")
            (root / "data" / "blob").write_bytes(b"payload")

            manifest = build_manifest(root, "run-1")
            verify_manifest(root, manifest)

            (root / "data" / "blob").write_bytes(b"PAYLOAD")
            with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                verify_manifest(root, manifest)

    def test_manifest_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "state.db").write_bytes(b"sqlite")
            manifest = build_manifest(root, "run-1")
            manifest["files"]["../escape"] = {
                "sha256": "0" * 64,
                "size": 0,
            }
            with self.assertRaisesRegex(RuntimeError, "unsafe manifest path"):
                verify_manifest(root, manifest)

    def test_pointer_is_strict_and_binds_manifest_digest(self):
        manifest = {
            "schema_version": 1,
            "generation": "run-1",
            "files": {},
        }
        pointer = build_pointer("run-1", manifest)
        self.assertEqual(validate_pointer(pointer), "run-1")

        pointer["generation"] = "../other"
        with self.assertRaisesRegex(RuntimeError, "invalid generation"):
            validate_pointer(pointer)

    def test_manifest_json_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "state.db").write_bytes(b"sqlite")
            first = build_manifest(root, "run-1")
            second = build_manifest(root, "run-1")
            self.assertEqual(
                json.dumps(first, sort_keys=True),
                json.dumps(second, sort_keys=True),
            )


if __name__ == "__main__":
    unittest.main()
