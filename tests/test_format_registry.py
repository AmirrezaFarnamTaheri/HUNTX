import unittest
from unittest.mock import Mock
from huntx.formats.registry import FormatRegistry


class TestFormatRegistry(unittest.TestCase):
    def setUp(self):
        # Explicitly reset the singleton state before each test
        FormatRegistry._instance = None
        self.registry = FormatRegistry.get_instance()
        # Clear handlers
        self.registry._handlers.clear()

    def test_singleton(self):
        reg1 = FormatRegistry.get_instance()
        reg2 = FormatRegistry.get_instance()
        self.assertIs(reg1, reg2)

    def test_register_and_get(self):
        handler = Mock()
        handler.format_id = "test_fmt"

        self.registry.register(handler)
        self.assertIn("test_fmt", self.registry.list_formats())

        retrieved = self.registry.get("test_fmt")
        self.assertIs(retrieved, handler)

    def test_get_unknown(self):
        self.assertIsNone(self.registry.get("unknown_fmt"))

    def test_overwrite_handler(self):
        h1 = Mock()
        h1.format_id = "fmt"

        h2 = Mock()
        h2.format_id = "fmt"

        self.registry.register(h1)
        self.registry.register(h2)

        self.assertIs(self.registry.get("fmt"), h2)


if __name__ == "__main__":
    unittest.main()
