"""Unit tests for environment-variable expansion in configuration values.

These lock in the *deterministic failure* contract: a bare ``${VAR}`` is a
required value and must raise when unset, while the explicit ``${VAR:-default}``
fallback syntax is the sanctioned escape hatch for optional/dev values.
"""

import os
import unittest

from huntx.config.env_expand import expand_env, recursive_expand


class TestExpandEnv(unittest.TestCase):
    def setUp(self):
        # Ensure a clean slate for the sentinel variables used below.
        for key in ("HX_TEST_PRESENT", "HX_TEST_ABSENT"):
            os.environ.pop(key, None)

    def tearDown(self):
        for key in ("HX_TEST_PRESENT", "HX_TEST_ABSENT"):
            os.environ.pop(key, None)

    def test_present_variable_is_substituted(self):
        os.environ["HX_TEST_PRESENT"] = "value123"
        self.assertEqual(expand_env("api=${HX_TEST_PRESENT}"), "api=value123")

    def test_missing_required_variable_raises(self):
        with self.assertRaises(ValueError) as cm:
            expand_env("api=${HX_TEST_ABSENT}")
        self.assertIn("HX_TEST_ABSENT", str(cm.exception))

    def test_missing_variable_with_default_uses_default(self):
        self.assertEqual(expand_env("api=${HX_TEST_ABSENT:-fallback}"), "api=fallback")

    def test_empty_default_is_honored(self):
        # ``${VAR:-}`` is the explicit opt-in for an optional/empty value.
        self.assertEqual(expand_env("api=${HX_TEST_ABSENT:-}"), "api=")

    def test_present_variable_overrides_default(self):
        os.environ["HX_TEST_PRESENT"] = "real"
        self.assertEqual(expand_env("${HX_TEST_PRESENT:-fallback}"), "real")

    def test_multiple_references_in_one_string(self):
        os.environ["HX_TEST_PRESENT"] = "a"
        self.assertEqual(
            expand_env("${HX_TEST_PRESENT}-${HX_TEST_ABSENT:-b}"), "a-b"
        )

    def test_text_without_references_is_unchanged(self):
        self.assertEqual(expand_env("plain-string"), "plain-string")

    def test_recursive_expand_walks_nested_structures(self):
        os.environ["HX_TEST_PRESENT"] = "42"
        data = {
            "a": "${HX_TEST_PRESENT}",
            "b": ["${HX_TEST_ABSENT:-x}", {"c": "${HX_TEST_PRESENT}"}],
            "d": 7,  # non-string values pass through untouched
        }
        self.assertEqual(
            recursive_expand(data),
            {"a": "42", "b": ["x", {"c": "42"}], "d": 7},
        )

    def test_recursive_expand_propagates_missing_required(self):
        with self.assertRaises(ValueError):
            recursive_expand({"a": "${HX_TEST_ABSENT}"})


if __name__ == "__main__":
    unittest.main()
