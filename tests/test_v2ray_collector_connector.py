import unittest
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock
from huntx.connectors.v2ray_collector.connector import V2RayCollectorConnector


class TestV2RayCollectorConnector(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.connector = V2RayCollectorConnector(base_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("subprocess.run")
    def test_list_new_success(self, mock_run):
        # 1. Setup mock output file
        output_file = os.path.join(self.test_dir, "collected_configs.txt")
        mock_configs = [
            "ss://Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTpZNUVKWm9qVk1FTnZrRFZG@62.133.63.169:37096#Config1",
            "vless://3f3bb5cc-da8b-4551-8b76-ba223f1a5255@18.192.50.101:443?security=none#Config2",
        ]

        # Setup subprocess run mock to create the file (simulating Go collector execution)
        def side_effect(*args, **kwargs):
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("\n".join(mock_configs) + "\n")
            mock_res = MagicMock()
            mock_res.stdout = "Scraped successfully"
            mock_res.stderr = ""
            return mock_res

        mock_run.side_effect = side_effect

        # 2. Call the connector
        items = list(self.connector.list_new(state=None))

        # 3. Assertions
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].data.decode("utf-8"), mock_configs[0])
        self.assertEqual(items[1].data.decode("utf-8"), mock_configs[1])
        self.assertTrue(items[0].external_id.startswith("goscrap_"))
        self.assertEqual(items[0].metadata["filename"], "collected_configs.txt")
        self.assertTrue(self.connector.get_state()["last_run_time"] > 0)
        self.assertEqual(mock_run.call_count, 1)

    @patch("subprocess.run")
    def test_list_new_no_output_file(self, mock_run):
        # Subprocess runs but doesn't write output file
        mock_res = MagicMock()
        mock_res.stdout = ""
        mock_res.stderr = "Error"
        mock_run.return_value = mock_res

        items = list(self.connector.list_new(state=None))
        self.assertEqual(len(items), 0)
        self.assertEqual(mock_run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
