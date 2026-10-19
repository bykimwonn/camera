import json
import tempfile
import unittest
from pathlib import Path

from core.config import ConfigManager


class ConfigMigrationTests(unittest.TestCase):
    def test_eye_mode_migrates_to_head_without_discarding_saved_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            legacy_calibration = [[float(i == j) for j in range(2)] for i in range(5)]
            path.write_text(json.dumps({
                "config_version": 5,
                "control_mode": "Eye",
                "eye_calibration": legacy_calibration,
                "head_dwell_seconds": 1.5,
            }), encoding="utf-8")

            config = ConfigManager(path).data

            self.assertEqual(config["control_mode"], "Head")
            self.assertEqual(config["head_dwell_seconds"], 1.5)
            self.assertEqual(config["eye_calibration"], legacy_calibration)
            self.assertEqual(config["config_version"], 7)


if __name__ == "__main__":
    unittest.main()
