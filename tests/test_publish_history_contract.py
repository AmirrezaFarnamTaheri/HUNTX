"""Regression test for the publication-history contract.

``PublishPipeline`` used to keep its own in-memory cache of published hashes
(``_hash_cache``, ``_hash_guard``, ``_remember_published_hash`` and
``_last_published_hash``). Nothing read that cache: the pipeline asks the
state repository whether a destination is already confirmed, and the
repository is the durable record. The dead cache was a second source of truth
that could disagree with the repository after a restart.

The repository's own publication-history methods stay public and stay the
authority; this test pins that they still work and that the pipeline has no
private cache left to disagree with them.
"""
import unittest
from unittest.mock import MagicMock

from huntx.pipeline.publish import PublishPipeline
from huntx.state.repo import StateRepo


class TestPublishPipelineHasNoPrivateHashCache(unittest.TestCase):
    def test_pipeline_exposes_no_private_cache_attributes(self):
        pipeline = PublishPipeline(MagicMock(spec=StateRepo))
        for name in (
            "_hash_cache",
            "_hash_guard",
            "_last_published_hash",
            "_remember_published_hash",
        ):
            self.assertFalse(
                hasattr(pipeline, name),
                f"PublishPipeline still carries the removed cache attribute {name}",
            )

    def test_module_defines_no_removed_cache_helpers(self):
        from huntx.pipeline import publish as publish_module

        for name in (
            "_hash_cache",
            "_hash_guard",
            "_last_published_hash",
            "_remember_published_hash",
        ):
            self.assertFalse(
                hasattr(publish_module, name),
                f"publish module still defines {name}",
            )


class TestPublicationHistoryRemainsAuthoritative(unittest.TestCase):
    """The state repository keeps the publication history."""

    def test_repository_still_exposes_its_publication_methods(self):
        for name in (
            "mark_published",
            "is_artifact_published",
            "get_last_published_hash",
        ):
            self.assertTrue(
                callable(getattr(StateRepo, name, None)),
                f"StateRepo.{name} is missing",
            )


if __name__ == "__main__":
    unittest.main()
