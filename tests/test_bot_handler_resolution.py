"""Guard the bot's method-resolution invariants.

``HandlersMixin`` previously carried its own ``_on_callback`` and
``_check_rate_limit`` that were dead because ``InteractiveBot`` defines both in
its own class body (the class body always wins over a base). The dead copies
were a latent hazard rather than merely redundant:

* the dead ``_on_callback`` echoed raw exception text back to the user
  (``event.answer(f"Error: {e}")``), leaking internal detail;
* the dead ``_check_rate_limit`` never pruned ``_user_cooldowns``, so it grew
  without bound.

Any reordering of the base list, or removal of an override, would have silently
activated them. They are deleted; these tests fail if either creeps back or if
the hardened implementations stop being the ones that resolve.
"""

import inspect
import unittest

from huntx.bot import handlers
from huntx.bot.interactive import InteractiveBot

_SECURITY_CRITICAL = ("_on_callback", "_check_rate_limit")


class TestBotHandlerResolution(unittest.TestCase):
    def test_hardened_implementations_are_the_ones_used(self):
        for name in _SECURITY_CRITICAL:
            with self.subTest(method=name):
                func = getattr(InteractiveBot, name)
                source_file = inspect.getsourcefile(func) or ""
                self.assertTrue(
                    source_file.endswith("interactive.py"),
                    f"{name} resolved to {source_file}, not the hardened "
                    "implementation in interactive.py",
                )

    def test_handlers_mixin_does_not_redefine_them(self):
        for name in _SECURITY_CRITICAL:
            with self.subTest(method=name):
                self.assertNotIn(
                    name,
                    vars(handlers.HandlersMixin),
                    f"HandlersMixin re-defines {name}; a shadowed duplicate is a "
                    "latent security regression (see this module's docstring)",
                )

    def test_active_rate_limiter_prunes_its_cooldown_map(self):
        # The bound on _user_cooldowns is what keeps a public command from
        # growing memory without limit, so assert the pruning call survives.
        src = inspect.getsource(InteractiveBot._check_rate_limit)
        self.assertIn("_prune_cooldowns", src)

    def test_active_callback_does_not_echo_exception_text(self):
        src = inspect.getsource(InteractiveBot._on_callback)
        self.assertNotIn(
            'f"Error: {e}"',
            src,
            "callback handler leaks raw exception text to the user",
        )


if __name__ == "__main__":
    unittest.main()
