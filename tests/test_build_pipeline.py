import unittest
from unittest.mock import Mock
from mergebot.pipeline.build import BuildPipeline

class TestBuildPipeline(unittest.TestCase):
    def setUp(self):
        self.state_repo = Mock()
        self.artifact_store = Mock()
        self.registry = Mock()
        self.pipeline = BuildPipeline(self.state_repo, self.artifact_store, self.registry)

    def test_build_success(self):
        route_config = {
            "name": "route1",
            "formats": ["fmt1"],
            "from_sources": ["src1"]
        }

        self.state_repo.get_records_for_build.return_value = ["rec1", "rec2"]

        handler = Mock()
        handler.build.return_value = b"artifact data"
        self.registry.get.return_value = handler

        self.artifact_store.save_artifact.return_value = "art_hash"

        results = self.pipeline.run(route_config)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["artifact_hash"], "art_hash")
        self.artifact_store.save_output.assert_called_with("route1", "fmt1", b"artifact data")

    def test_build_no_records(self):
        route_config = {
            "name": "route1",
            "formats": ["fmt1"],
            "from_sources": ["src1"]
        }
        self.state_repo.get_records_for_build.return_value = []

        results = self.pipeline.run(route_config)

        self.assertEqual(len(results), 0)
        self.artifact_store.save_artifact.assert_not_called()

if __name__ == '__main__':
    unittest.main()
