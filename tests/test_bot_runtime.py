import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
import os
import asyncio
from huntx.bot.interactive import InteractiveBot

class TestBotRuntime(unittest.TestCase):
    def setUp(self):
        # Mock paths.STATE_DB_PATH and paths.DATA_DIR to avoid side effects during init
        with patch('huntx.store.paths.STATE_DB_PATH', Path('./temp_state.db')), \
             patch('huntx.store.paths.DATA_DIR', Path('./temp_bot_init')):
            self.bot = InteractiveBot(
                token="123:abc",
                api_id=123,
                api_hash="hash"
            )
        # Mock the Telethon client methods as AsyncMocks
        self.bot.client = MagicMock()
        self.bot.client.start = AsyncMock()
        self.bot.client.send_file = AsyncMock()
        self.bot.client.send_message = AsyncMock()

    def test_send_format_to_user_paths_usage(self):
        """Verify that _send_format_to_user uses paths.OUTPUT_DIR correctly."""
        temp_dir = Path("./temp_test_output")
        temp_dir.mkdir(exist_ok=True)
        
        output_dir = temp_dir / "output"
        output_dir.mkdir(exist_ok=True)
        
        # Create a dummy file
        test_file = output_dir / "all_sources.npvt"
        test_file.write_text("vmess://test")
        
        # We need to make the async call
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            with patch('huntx.store.paths.OUTPUT_DIR', output_dir):
                loop.run_until_complete(self.bot._send_format_to_user(12345, "npvt"))
            
            # Verify send_file was called with the correct path
            self.bot.client.send_file.assert_called()
            call_args = self.bot.client.send_file.call_args
            self.assertEqual(call_args[0][0], 12345)
            # Use resolve() to compare paths consistently
            self.assertEqual(call_args[0][1].resolve(), test_file.resolve())
        finally:
            # Cleanup
            test_file.unlink()
            output_dir.rmdir()
            temp_dir.rmdir()
            loop.close()

    def test_deliver_updates_paths_usage(self):
        """Verify that deliver_updates uses paths.OUTPUT_DIR correctly."""
        temp_dir = Path("./temp_test_deliver")
        temp_dir.mkdir(exist_ok=True)

        output_dir = temp_dir / "output"
        output_dir.mkdir(exist_ok=True)
        
        # Create a dummy file
        test_file = output_dir / "all_sources.npvt"
        test_file.write_text("vmess://test")
        
        # Mock _get_active_users
        self.bot._get_active_users = MagicMock(return_value=[{"user_id": "1", "chat_id": "10"}])
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            with patch('huntx.store.paths.OUTPUT_DIR', output_dir):
                loop.run_until_complete(self.bot.deliver_updates())
            
            # Verify send_file was called
            self.bot.client.send_file.assert_called()
        finally:
            test_file.unlink()
            output_dir.rmdir()
            temp_dir.rmdir()
            loop.close()

if __name__ == '__main__':
    unittest.main()
