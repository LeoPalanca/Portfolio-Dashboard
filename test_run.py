from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run


class BootstrapTest(unittest.TestCase):
    def test_writes_private_config_and_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config.toml"
            source = root / "source"
            data = root / "data"
            cache = root / "cache"
            with patch.object(run, "CONFIG_FILE", config):
                run.write_default_config(source, data, cache)
            content = config.read_text(encoding="utf-8")
            directories_exist = source.exists() and data.exists() and cache.exists()

        self.assertIn(f'source_dir = {json.dumps(str(source.resolve()))}', content)
        self.assertIn("scan_downloads = false", content)
        self.assertIn('edition_suffix = ""', content)
        self.assertIn('default_proxy_mode = "off"', content)
        self.assertTrue(directories_exist)


if __name__ == "__main__":
    unittest.main()
