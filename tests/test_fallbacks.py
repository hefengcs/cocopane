import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "monitor"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("gpu", SCRIPTS / "_pane_gpu.py")
gpu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gpu)


class FallbackTests(unittest.TestCase):
    def test_no_gpu_works_without_running_an_external_command(self):
        with patch.object(gpu.shutil, "which", return_value=None), patch.object(gpu.subprocess, "run") as run:
            lines = gpu.snapshot()
            run.assert_not_called()
            self.assertIn("No NVIDIA GPU", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
