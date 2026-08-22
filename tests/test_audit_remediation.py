import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huntx.cli.main import _cmd_reset
from huntx.core.run_health import evaluate_run_health
from huntx.publishers.telegram.publisher import TelegramPublisher
from huntx.state.repo import StateRepo


class TestAuditRemediation(unittest.TestCase):
    @patch("time.sleep")
    def test_telegram_publisher_validation(self, mock_sleep):
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 200
            mock_resp.read.return_value = b'{"ok": true, "result": {}}'
            mock_url.return_value.__enter__.return_value = mock_resp

            pub = TelegramPublisher("123:abc")
            res = pub.publish("12345", b"data", "file.txt", "cap")
            self.assertTrue(res["ok"])

            mock_resp.read.return_value = (
                b'{"ok": false, "description": "Too Many Requests", "parameters": {"retry_after": 42}}'
            )
            with self.assertRaises(RuntimeError) as cm:
                pub.publish("12345", b"data", "file.txt", "cap")
            self.assertIn("Too Many Requests", str(cm.exception))

    def test_repo_deterministic_published_lookup(self):
        mock_db = MagicMock()
        repo = StateRepo(mock_db)
        mock_cursor = MagicMock()
        mock_db.connect.return_value.__enter__.return_value.execute.return_value = mock_cursor

        repo.get_last_published_hash("route_a")

        call_args = mock_db.connect.return_value.__enter__.return_value.execute.call_args
        sql = call_args[0][0]
        self.assertIn("ORDER BY published_at DESC, id DESC", sql)

    @patch("shutil.rmtree")
    @patch("shutil.copy2")
    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists")
    @patch("builtins.input")
    def test_reset_command_confirmation(
        self,
        mock_input,
        mock_exists,
        mock_unlink,
        mock_copy2,
        mock_rmtree,
    ):
        mock_exists.return_value = True

        mock_input.return_value = "WRONG"
        args = MagicMock()
        args.yes = False

        with (
            patch("huntx.store.paths.DATA_DIR", Path("/tmp/data")),
            patch("huntx.store.paths.STATE_DB_PATH", "/tmp/state.db"),
        ):
            _cmd_reset(args)

        mock_rmtree.assert_not_called()
        mock_copy2.assert_not_called()

        mock_input.return_value = "RESET"
        with (
            patch("pathlib.Path.write_text"),
            patch("pathlib.Path.mkdir"),
            patch("huntx.store.paths.DATA_DIR", Path("/tmp/data")),
            patch("huntx.store.paths.STATE_DB_PATH", "/tmp/state.db"),
        ):
            _cmd_reset(args)

        mock_copy2.assert_called_once()
        self.assertTrue(mock_rmtree.called or mock_unlink.called)

    @patch("huntx.cli.commands.run.execute_pipeline_run")
    @patch("pathlib.Path.exists")
    def test_run_command_health_gate(self, mock_exists, mock_execute):
        mock_exists.return_value = True

        from huntx.cli.commands.run import run_command

        def execution(summary):
            return SimpleNamespace(
                summary=summary,
                health=evaluate_run_health(summary, no_publish=False),
            )

        mock_execute.return_value = execution(
            {
                "status": "completed",
                "total_artifacts": 0,
                "ingest_ok": 3,
                "publish_attempts": 0,
                "publish_failures": 0,
            }
        )
        run_command("dummy_config.yaml")

        mock_execute.return_value = execution(
            {
                "status": "partial",
                "total_artifacts": 1,
                "ingest_ok": 3,
                "publish_attempts": 2,
                "publish_failures": 2,
            }
        )
        run_command("dummy_config.yaml")

        mock_execute.return_value = execution(
            {
                "status": "failed",
                "reason": "no_approved_sources",
                "total_artifacts": 0,
                "ingest_ok": 0,
                "ingest_err": 0,
            }
        )
        with self.assertRaises(RuntimeError) as cm:
            run_command("dummy_config.yaml")
        self.assertIn("Health Gate FATAL", str(cm.exception))
        self.assertIn("no_approved_sources", str(cm.exception))

        mock_execute.return_value = execution(
            {
                "status": "completed",
                "total_artifacts": 1,
                "ingest_ok": 3,
                "publish_attempts": 2,
                "publish_failures": 0,
            }
        )
        run_command("dummy_config.yaml")


if __name__ == "__main__":
    unittest.main()
