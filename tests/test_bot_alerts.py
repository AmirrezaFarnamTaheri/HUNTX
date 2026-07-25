import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from huntx.bot.delivery import DeliveryMixin


class DummyBotDelivery(DeliveryMixin):
    def __init__(self):
        self.client = AsyncMock()


class TestBotAlerts(unittest.TestCase):
    def test_send_freshness_alert_normal(self):
        bot = DummyBotDelivery()
        bot.client.send_message.return_value = True

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(
                bot.send_freshness_alert(admin_chat_id=123456, proxy_count=50, min_threshold=10)
            )
            self.assertTrue(success)
            bot.client.send_message.assert_called_once()
            args, kwargs = bot.client.send_message.call_args
            self.assertEqual(args[0], 123456)
            self.assertIn("✅ [PIPELINE REPORT]", args[1])
            self.assertIn("Fresh Proxies Available: 50", args[1])
        finally:
            loop.close()

    def test_send_freshness_alert_low(self):
        bot = DummyBotDelivery()
        bot.client.send_message.return_value = True

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(
                bot.send_freshness_alert(admin_chat_id=123456, proxy_count=3, min_threshold=10)
            )
            self.assertTrue(success)
            args, kwargs = bot.client.send_message.call_args
            self.assertIn("⚠️ [LOW FRESHNESS WARNING]", args[1])
        finally:
            loop.close()
