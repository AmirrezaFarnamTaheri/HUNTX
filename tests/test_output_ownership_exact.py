"""Regression test for exact output ownership in the legacy export path.

``Orchestrator._export_outputs`` used to decide which files it owned with
``name.startswith(route)``. A prefix test made route "all" the owner of
"all_sources.fmt", so a run that stopped emitting one route could delete a
sibling route's artifact. Ownership is decided by exact filename now.
"""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from huntx.config.schema import (
    AppConfig,
    DestinationConfig,
    PublishRoute,
    PublishingConfig,
    SourceConfig,
    SourceSelector,
    TelegramSourceConfig,
)
from huntx.core.orchestrator import Orchestrator
from huntx.store import paths as paths_mod


def _config(route_specs) -> AppConfig:
    """Build a config from ``[(route_name, [formats]), ...]`` or plain names.

    A plain name gets the neutral ``fmt`` format; a pair names the route and
    the formats it builds, so a test can exercise the real proxy formats and
    their derivatives.
    """
    normalized = []
    for spec in route_specs:
        if isinstance(spec, str):
            normalized.append((spec, ["fmt"]))
        else:
            normalized.append((spec[0], list(spec[1])))
    return AppConfig(
        sources=[
            SourceConfig(
                id="src_bot",
                type="telegram",
                selector=SourceSelector(include_formats=["fmt"]),
                telegram=TelegramSourceConfig(token="000000:placeholder", chat_id="123"),
            ),
        ],
        publishing=PublishingConfig(
            routes=[
                PublishRoute(
                    name=name,
                    from_sources=["src_bot"],
                    formats=formats,
                    destinations=[
                        DestinationConfig(
                            chat_id="dest1",
                            mode="telegram",
                            caption_template="cap",
                        )
                    ],
                )
                for name, formats in normalized
            ]
        ),
    )


class TestExactOutputOwnership(unittest.TestCase):
    """A route may only delete a file it owns by exact name."""

    def _orchestrator(self, route_specs):
        return Orchestrator(_config(route_specs))

    def _bind_output_dir(self, orch, tmp):
        out_dir = Path(tmp) / "outputs"
        out_dir.mkdir()
        orch.paths = paths_mod.RuntimePaths(
            data_dir=Path(tmp),
            raw_store_dir=Path(tmp),
            artifact_store_dir=Path(tmp),
            rejects_dir=Path(tmp),
            state_dir=Path(tmp),
            logs_dir=Path(tmp),
            output_dir=out_dir,
            dev_output_dir=Path(tmp) / "dev",
            state_db_path=Path(tmp) / "state.db",
        )
        return out_dir

    @staticmethod
    def _age(path, days):
        stamp = time.time() - days * 86400
        os.utime(path, (stamp, stamp))

    @patch("huntx.core.orchestrator.RawStore")
    @patch("huntx.core.orchestrator.ArtifactStore")
    @patch("huntx.core.orchestrator.open_db")
    @patch("huntx.core.orchestrator.StateRepo")
    @patch("huntx.core.orchestrator.FormatRegistry")
    @patch("huntx.core.orchestrator.IngestionPipeline")
    @patch("huntx.core.orchestrator.TransformPipeline")
    @patch("huntx.core.orchestrator.BuildPipeline")
    @patch("huntx.core.orchestrator.PublishPipeline")
    def test_sibling_route_sharing_a_prefix_is_not_deleted(self, *args):
        """A route must not delete a file that only shares its name prefix.

        The prefix test matched "all_sources.fmt" against route "all",
        because the sibling's name starts with "all". Route "all_sources" is
        no longer configured, so nothing owns that file any more, but "all"
        does not own it either: ownership is by exact filename. The sibling
        artifact is older than the retention window, so a prefix-based owner
        would have deleted it.
        """
        orch = self._orchestrator(["all"])
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = self._bind_output_dir(orch, tmp)

            sibling = out_dir / orch._output_filename("all_sources", "fmt")
            sibling.write_text("sibling", encoding="utf-8")
            self._age(sibling, orch.OUTPUT_RETENTION_DAYS + 1)

            # The run emits only route "all"'s artifact.
            results = [{"route_name": "all", "format": "fmt", "data": b"new"}]
            orch._export_outputs(results)

            self.assertTrue(
                sibling.exists(),
                "a sibling route's artifact was deleted by a prefix match",
            )
            self.assertTrue(
                (out_dir / orch._output_filename("all", "fmt")).exists()
            )

    @patch("huntx.core.orchestrator.RawStore")
    @patch("huntx.core.orchestrator.ArtifactStore")
    @patch("huntx.core.orchestrator.open_db")
    @patch("huntx.core.orchestrator.StateRepo")
    @patch("huntx.core.orchestrator.FormatRegistry")
    @patch("huntx.core.orchestrator.IngestionPipeline")
    @patch("huntx.core.orchestrator.TransformPipeline")
    @patch("huntx.core.orchestrator.BuildPipeline")
    @patch("huntx.core.orchestrator.PublishPipeline")
    def test_own_stale_file_is_still_pruned(self, *args):
        """Exact ownership must not stop a route's own stale file from being pruned."""
        orch = self._orchestrator(["route1"])
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = self._bind_output_dir(orch, tmp)

            owned = out_dir / orch._output_filename("route1", "fmt")
            owned.write_text("stale", encoding="utf-8")
            self._age(owned, orch.OUTPUT_RETENTION_DAYS + 1)

            results = [{"route_name": "route1", "format": "fmt", "data": b"new"}]
            orch._export_outputs(results)

            current = out_dir / orch._output_filename("route1", "fmt")
            self.assertTrue(current.exists())
            self.assertEqual(current.read_bytes(), b"new")

    @patch("huntx.core.orchestrator.RawStore")
    @patch("huntx.core.orchestrator.ArtifactStore")
    @patch("huntx.core.orchestrator.open_db")
    @patch("huntx.core.orchestrator.StateRepo")
    @patch("huntx.core.orchestrator.FormatRegistry")
    @patch("huntx.core.orchestrator.IngestionPipeline")
    @patch("huntx.core.orchestrator.TransformPipeline")
    @patch("huntx.core.orchestrator.BuildPipeline")
    @patch("huntx.core.orchestrator.PublishPipeline")
    def test_unrelated_file_is_never_deleted(self, *args):
        """A file that is not an exact output name is never a pruning candidate."""
        orch = self._orchestrator(["route1"])
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = self._bind_output_dir(orch, tmp)

            helper = out_dir / "README.md"
            helper.write_text("keep me", encoding="utf-8")
            self._age(helper, orch.OUTPUT_RETENTION_DAYS + 1)

            results = [{"route_name": "route1", "format": "fmt", "data": b"new"}]
            orch._export_outputs(results)

            self.assertTrue(helper.exists())

    @patch("huntx.core.orchestrator.RawStore")
    @patch("huntx.core.orchestrator.ArtifactStore")
    @patch("huntx.core.orchestrator.open_db")
    @patch("huntx.core.orchestrator.StateRepo")
    @patch("huntx.core.orchestrator.FormatRegistry")
    @patch("huntx.core.orchestrator.IngestionPipeline")
    @patch("huntx.core.orchestrator.TransformPipeline")
    @patch("huntx.core.orchestrator.BuildPipeline")
    @patch("huntx.core.orchestrator.PublishPipeline")
    def test_derivative_names_of_a_derived_format_are_owned(self, *args):
        """npvt's derivative products are owned by exact name too."""
        orch = self._orchestrator([("route1", ["npvt", "npvtsub", "fmt"])])
        with tempfile.TemporaryDirectory() as tmp:
            self._bind_output_dir(orch, tmp)

            owned = orch._owned_output_filenames()
            # The base format and every derivative the build pipeline derives
            # from it are owned. The derivative identities are the ones the
            # build pipeline actually emits ("npvt.decoded.json" and friends),
            # mapped through the shared naming contract.
            self.assertIn(orch._output_filename("route1", "npvt"), owned)
            self.assertIn(orch._output_filename("route1", "npvt.decoded.json"), owned)
            self.assertIn(orch._output_filename("route1", "npvt.b64sub"), owned)
            self.assertIn(orch._output_filename("route1", "npvtsub"), owned)
            self.assertIn(orch._output_filename("route1", "npvtsub.b64sub"), owned)
            # A format that produces no derivatives is owned by one name only.
            self.assertIn(orch._output_filename("route1", "fmt"), owned)
            self.assertNotIn(orch._output_filename("route1", "fmt.decoded.json"), owned)


if __name__ == "__main__":
    unittest.main()
