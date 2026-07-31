import json
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tap_ga360 import config


class TestGetArgs(unittest.TestCase):

    @patch("sys.argv", ["config", "--config", "config.json", "--creds", "creds.json"])
    def test_get_args_parses_paths(self):
        args = config.get_args()
        self.assertEqual(args.config, "config.json")
        self.assertEqual(args.creds, "creds.json")


class TestWriteConfig(unittest.TestCase):

    def test_write_config_embeds_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            creds_path = tmp_path / "creds.json"
            config_path = tmp_path / "config.json"
            creds_path.write_text(json.dumps({"private_key": "secret"}))
            # Append trailing content to verify seek(0)+dump works on the JSON portion
            config_path.write_text(json.dumps({"project_id": "project"}))

            config.write_config(str(config_path), str(creds_path))

            written, _ = json.JSONDecoder().raw_decode(config_path.read_text())
            self.assertEqual(
                written,
                {
                    "project_id": "project",
                    "credentials": json.dumps({"private_key": "secret"}),
                },
            )


class TestConfigModuleEntrypoint(unittest.TestCase):

    def test_config_module_entrypoint_writes_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            creds_path = tmp_path / "creds.json"
            config_path = tmp_path / "config.json"
            creds_path.write_text("{}")
            config_path.write_text("{}")

            with patch(
                "sys.argv",
                ["config", "--config", str(config_path), "--creds", str(creds_path)],
            ):
                runpy.run_module("tap_ga360.config", run_name="__main__")

            self.assertEqual(json.loads(config_path.read_text())["credentials"], "{}")
