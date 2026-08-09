import concurrent.futures
import unittest
from unittest.mock import Mock, patch

from huntx.pipeline.build import BuildPipeline
from huntx.pipeline.governed_build import GovernedBuildPipeline


class TestBuildPipeline(unittest.TestCase):
    def setUp(self):
        self.state_repo = Mock()
        self.artifact_store = Mock()
        self.registry = Mock()
        self.pipeline = BuildPipeline(
            self.state_repo,
            self.artifact_store,
            self.registry,
        )

    def test_build_success(self):
        route_config = {
            "name": "route1",
            "formats": ["fmt1"],
            "from_sources": ["src1"],
        }
        self.state_repo.get_records_for_build.return_value = [
            {"record_type": "fmt1", "data": "data1"},
            {"record_type": "fmt1", "data": "data2"},
        ]
        handler = Mock()
        handler.build.return_value = b"artifact data"
        self.registry.get.return_value = handler
        self.artifact_store.save_artifact.return_value = "art_hash"

        results = self.pipeline.run(route_config)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["artifact_hash"], "art_hash")
        self.assertEqual(results[0]["count"], 2)
        handler.build.assert_called_once_with(
            [
                {"record_type": "fmt1", "data": "data1"},
                {"record_type": "fmt1", "data": "data2"},
            ]
        )
        self.artifact_store.save_output.assert_called_with("route1", "fmt1", b"artifact data")

    def test_build_no_records(self):
        route_config = {
            "name": "route1",
            "formats": ["fmt1"],
            "from_sources": ["src1"],
        }
        self.state_repo.get_records_for_build.return_value = []

        results = self.pipeline.run(route_config)

        self.assertEqual(len(results), 0)
        self.artifact_store.save_artifact.assert_not_called()

    def test_build_passes_min_seen_file_id(self):
        route_config = {
            "name": "route1",
            "formats": ["fmt1"],
            "from_sources": ["src1"],
            "min_seen_file_id": 55,
        }
        self.state_repo.get_records_for_build.return_value = []

        self.pipeline.run(route_config)

        self.state_repo.get_records_for_build.assert_called_once_with(["fmt1"], ["src1"], min_seen_file_id=55)

    def test_groups_records_once_and_uses_per_format_counts(self):
        route_config = {
            "name": "route1",
            "formats": ["fmt1", "fmt2"],
            "from_sources": ["src1"],
        }
        records = [
            {"record_type": "fmt1", "data": "a"},
            {"record_type": "fmt2", "data": "b"},
            {"record_type": "fmt1", "data": "c"},
        ]
        self.state_repo.get_records_for_build.return_value = records
        fmt1_handler = Mock()
        fmt1_handler.build.return_value = b"one"
        fmt2_handler = Mock()
        fmt2_handler.build.return_value = b"two"
        self.registry.get.side_effect = lambda fmt: {
            "fmt1": fmt1_handler,
            "fmt2": fmt2_handler,
        }[fmt]
        self.artifact_store.save_artifact.side_effect = lambda _, fmt, __: f"hash-{fmt}"

        results = self.pipeline.run(route_config)

        by_format = {result["format"]: result for result in results}
        self.assertEqual(by_format["fmt1"]["count"], 2)
        self.assertEqual(by_format["fmt2"]["count"], 1)
        fmt1_handler.build.assert_called_once_with([records[0], records[2]])
        fmt2_handler.build.assert_called_once_with([records[1]])

    def test_duplicate_formats_and_sources_are_deduplicated(self):
        route_config = {
            "name": "route1",
            "formats": ["fmt1", "fmt1"],
            "from_sources": ["src1", "src1"],
        }
        self.state_repo.get_records_for_build.return_value = [{"record_type": "fmt1", "data": "a"}]
        handler = Mock()
        handler.build.return_value = b"artifact"
        self.registry.get.return_value = handler
        self.artifact_store.save_artifact.return_value = "hash"

        results = self.pipeline.run(route_config)

        self.state_repo.get_records_for_build.assert_called_once_with(["fmt1"], ["src1"], min_seen_file_id=None)
        handler.build.assert_called_once()
        self.assertEqual([result["format"] for result in results], ["fmt1"])

    def test_records_can_be_injected_without_query(self):
        route_config = {
            "name": "route1",
            "formats": ["fmt1"],
            "from_sources": ["src1"],
        }
        handler = Mock()
        handler.build.return_value = b"artifact"
        self.registry.get.return_value = handler
        self.artifact_store.save_artifact.return_value = "hash"

        results = self.pipeline.run(
            route_config,
            records=[{"record_type": "fmt1", "data": "a"}],
        )

        self.state_repo.get_records_for_build.assert_not_called()
        self.assertEqual(results[0]["count"], 1)


class TestGovernedBuildPipeline(unittest.TestCase):
    @patch("huntx.pipeline.governed_build.get_records_for_governed_build")
    def test_equivalent_routes_share_one_governed_query(self, governed_query):
        state_repo = Mock()
        state_repo.db = Mock()
        artifact_store = Mock()
        artifact_store.save_artifact.side_effect = lambda route, fmt, data: f"{route}-{fmt}"
        registry = Mock()
        handler = Mock()
        handler.build.return_value = b"artifact"
        registry.get.return_value = handler
        governed_query.return_value = [{"record_type": "fmt1", "data": "a"}]
        pipeline = GovernedBuildPipeline(
            state_repo,
            artifact_store,
            registry,
            {"route1": ("compatible", False), "route2": ("compatible", False)},
        )
        routes = [
            {
                "name": "route1",
                "formats": ["fmt1"],
                "from_sources": ["src1"],
                "min_seen_file_id": 7,
            },
            {
                "name": "route2",
                "formats": ["fmt1"],
                "from_sources": ["src1"],
                "min_seen_file_id": 7,
            },
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(pipeline.run, routes))

        governed_query.assert_called_once_with(
            state_repo.db,
            ["fmt1"],
            ["src1"],
            min_seen_file_id=7,
            publication_tier="compatible",
            require_fresh_probe=False,
        )
        self.assertEqual([items[0]["route_name"] for items in results], ["route1", "route2"])


if __name__ == "__main__":
    unittest.main()
