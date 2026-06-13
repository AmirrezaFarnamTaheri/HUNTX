import unittest
from unittest.mock import MagicMock, patch, mock_open
import io
import json
from pathlib import Path
from huntx.publishers.telegram.publisher import TelegramPublisher
from huntx.state.repo import StateRepo
from huntx.cli.main import _cmd_reset

class TestAuditRemediation(unittest.TestCase):
    @patch('time.sleep')
    def test_telegram_publisher_validation(self, mock_sleep):
        # Mock urllib.request.urlopen
        with patch('urllib.request.urlopen') as mock_url:
            # Case 1: ok is True
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 200
            mock_resp.read.return_value = b'{"ok": true, "result": {}}'
            mock_url.return_value.__enter__.return_value = mock_resp
            
            pub = TelegramPublisher("123:abc")
            res = pub.publish("12345", b"data", "file.txt", "cap")
            self.assertTrue(res["ok"])
            
            # Case 2: ok is False
            mock_resp.read.return_value = b'{"ok": false, "description": "Too Many Requests", "parameters": {"retry_after": 42}}'
            with self.assertRaises(RuntimeError) as cm:
                pub.publish("12345", b"data", "file.txt", "cap")
            self.assertIn("Too Many Requests", str(cm.exception))

    def test_repo_deterministic_published_lookup(self):
        mock_db = MagicMock()
        repo = StateRepo(mock_db)
        
        # Mock cursor for execute
        mock_cursor = MagicMock()
        mock_db.connect.return_value.__enter__.return_value.execute.return_value = mock_cursor
        
        repo.get_last_published_hash("route_a")
        
        # Verify ORDER BY
        call_args = mock_db.connect.return_value.__enter__.return_value.execute.call_args
        sql = call_args[0][0]
        self.assertIn("ORDER BY published_at DESC, id DESC", sql)

    @patch('shutil.rmtree')
    @patch('pathlib.Path.unlink')
    @patch('pathlib.Path.exists')
    @patch('builtins.input')
    def test_reset_command_confirmation(self, mock_input, mock_exists, mock_unlink, mock_rmtree):
        mock_exists.return_value = True
        
        # Case 1: Wrong confirmation
        mock_input.return_value = "WRONG"
        args = MagicMock()
        args.yes = False
        
        with patch('huntx.store.paths.DATA_DIR', Path('/tmp/data')), \
             patch('huntx.store.paths.STATE_DB_PATH', '/tmp/state.db'):
            _cmd_reset(args)
            
        mock_rmtree.assert_not_called()
        
        # Case 2: Correct confirmation
        mock_input.return_value = "RESET"
        # We need to mock Path.write_text too as it recreates READMEs
        with patch('pathlib.Path.write_text'), \
             patch('pathlib.Path.mkdir'), \
             patch('huntx.store.paths.DATA_DIR', Path('/tmp/data')), \
             patch('huntx.store.paths.STATE_DB_PATH', '/tmp/state.db'):
            _cmd_reset(args)
            
        self.assertTrue(mock_rmtree.called or mock_unlink.called)

    @patch('huntx.cli.commands.run.load_config')
    @patch('huntx.cli.commands.run.validate_config')
    @patch('huntx.cli.commands.run.acquire_lock')
    @patch('huntx.cli.commands.run.Orchestrator')
    @patch('pathlib.Path.exists')
    def test_run_command_health_gate(self, mock_exists, MockOrch, mock_lock, mock_val, mock_load):
        mock_exists.return_value = True
        mock_orch_inst = MockOrch.return_value
        
        from huntx.cli.commands.run import run_command
        
        # Case 1: zero artifacts built
        mock_orch_inst.run.return_value = {"total_artifacts": 0, "publish_attempts": 0, "publish_failures": 0}
        with self.assertRaises(RuntimeError) as cm:
            run_command("dummy_config.yaml")
        self.assertIn("Zero artifacts were built", str(cm.exception))
        
        # Case 2: publish attempted but all failed
        mock_orch_inst.run.return_value = {"total_artifacts": 1, "publish_attempts": 2, "publish_failures": 2}
        with self.assertRaises(RuntimeError) as cm:
            run_command("dummy_config.yaml")
        self.assertIn("all publish tasks failed", str(cm.exception))
        
        # Case 3: successful run
        mock_orch_inst.run.return_value = {"total_artifacts": 1, "publish_attempts": 2, "publish_failures": 0}
        run_command("dummy_config.yaml")  # Should not raise any error


if __name__ == '__main__':
    unittest.main()

