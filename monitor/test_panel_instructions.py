import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("launch_agent", SCRIPTS / "_launch_agent.py")
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


class PanelInstructionsTests(unittest.TestCase):
    def test_rules_have_current_slot_and_self_contained_binding(self):
        rules, values = launch.panel_context({
            "COCO_SLOT": "7", "COCO_LOG_DIR": "/tmp/log dir ' quoted",
        })
        self.assertIn('COCO_SLOT="7"', rules)
        self.assertEqual(values["COCO_LOG_PATH"], "/tmp/log dir ' quoted/latest7.log")
        self.assertIn("set-log", rules)
        self.assertNotIn("<当前窗口的绑定命令>", rules)
        self.assertIn("COCO_LOG_DIR=", rules)

    def test_codex_preserves_existing_instructions_in_all_modes(self):
        rules, values = launch.panel_context({"COCO_SLOT": "2"})
        with patch.object(launch, "UsageClient") as factory:
            factory.return_value.call.return_value = {"config": {"developer_instructions": "Existing custom rules"}}
            for mode, suffix in (("new", []), ("resume", ["resume"]), ("continue", ["resume", "--last"])):
                args = launch.codex_args("/bin/codex", rules, values, mode)
                injection = next(arg for arg in args if arg.startswith("developer_instructions="))
                self.assertEqual(json.loads(injection.split("=", 1)[1]), "Existing custom rules\n\n" + rules)
                self.assertIn('shell_environment_policy.set.COCO_SLOT="2"', args)
                self.assertEqual(args[args.index("--add-dir") + 1], values["COCO_LOG_DIR"])
                self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)
                if suffix:
                    self.assertEqual(args[-len(suffix):], suffix)
            self.assertEqual(factory.return_value.close.call_count, 3)

    def test_unsafe_and_no_instructions_are_explicit(self):
        rules, values = launch.panel_context({"COCO_SLOT": "2"})
        with patch.object(launch, "UsageClient") as factory:
            args = launch.codex_args("/bin/codex", rules, values, "new", unsafe=True, inject=False)
            factory.assert_not_called()
            self.assertIn("--dangerously-bypass-approvals-and-sandbox", args)
            self.assertFalse(any(arg.startswith("developer_instructions=") for arg in args))

    def test_claude_receives_append_prompt_on_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "claude"
            output = Path(tmp) / "args.json"
            binary.write_text("#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\nPath(" + repr(str(output)) + ").write_text(json.dumps(sys.argv[1:]))\n")
            binary.chmod(0o755)
            for mode in ("new", "resume", "continue"):
                subprocess.run(["python3", str(SCRIPTS / "_launch_agent.py"), "--agent", "claude", "--binary", str(binary), "--mode", mode], env=dict(os.environ, COCO_SLOT="4"), check=True)
                args = json.loads(output.read_text())
                rules = args[args.index("--append-system-prompt") + 1]
                self.assertIn('COCO_SLOT="4"', rules)
                if mode != "new":
                    self.assertEqual(args[-1], "--" + mode)


class LogBindingTests(unittest.TestCase):
    def test_default_slot_override_and_preserve_regular_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / "monitor logs"
            logs.mkdir()
            job = root / "job ' $(unused).log"
            job.write_text("original output\n")
            env = dict(os.environ, COCO_LOG_DIR=str(logs), COCO_SLOT="3")
            def bind(*args, **overrides):
                return subprocess.run(["bash", str(SCRIPTS / "set_latest_log.sh"), *args], env=dict(env, **overrides), capture_output=True, text=True)
            self.assertEqual(bind(str(job)).returncode, 0)
            self.assertEqual((logs / "latest3.log").resolve(), job)
            self.assertFalse((logs / "latest.log").exists())
            self.assertEqual(bind("--slot", "2", str(job)).returncode, 0)
            self.assertEqual((logs / "latest2.log").resolve(), job)
            self.assertEqual(bind(str(job), COCO_SLOT="../bad").returncode, 2)
            existing = logs / "latest4.log"
            existing.write_text("keep me")
            self.assertNotEqual(bind("--slot", "4", str(job)).returncode, 0)
            self.assertEqual(existing.read_text(), "keep me")
            self.assertEqual(job.read_text(), "original output\n")


if __name__ == "__main__":
    unittest.main()
