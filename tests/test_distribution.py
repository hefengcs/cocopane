import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="coco-distribution-")
        self.root = Path(self.temp.name)
        self.home = self.root / "new user"
        self.home.mkdir()
        self.bin = self.root / "fake bin"
        self.bin.mkdir()
        (self.bin / "python3").symlink_to(sys.executable)
        self.records = self.root / "records"
        self.records.mkdir()
        self.fake = self.bin / "fake agent"
        self.fake.write_text('''#!/usr/bin/env python3
import json,os,sys,time
from pathlib import Path
if 'app-server' in sys.argv:
    for line in sys.stdin:
        request=json.loads(line)
        if 'id' not in request: continue
        method=request['method']
        if method=='initialize': result={}
        elif method=='config/read': result={'config':{'developer_instructions':'PRESERVE_MY_RULES'}}
        elif method=='account/rateLimits/read': result={'rateLimits':{'planType':'test','primary':{'usedPercent':25,'windowDurationMins':300}}}
        else: raise RuntimeError('Unexpected API operation: '+method)
        print(json.dumps({'id':request['id'],'result':result}),flush=True)
else:
    selected={key:os.environ.get(key) for key in ['COCO_SLOT','COCO_LOG_DIR','COCO_LOG_PATH','COCO_COMMAND','TEST_AUTH_VALUE']}
    record=Path(os.environ['COCO_RECORD_DIR'])/(os.environ['COCO_SLOT']+'.json')
    record.write_text(json.dumps({'args':sys.argv[1:],'env':selected}))
    print('Fake agent ready',flush=True)
    time.sleep(300)
''')
        self.fake.chmod(0o755)
        # Deterministic GPU error path on machines both with and without a GPU.
        (self.bin / "nvidia-smi").write_text("#!/bin/sh\nexit 1\n")
        (self.bin / "nvidia-smi").chmod(0o755)
        self.socket = "coco-test-" + uuid.uuid4().hex[:10]
        self.env = {
            "HOME": str(self.home), "PATH": str(self.bin) + ":/usr/bin:/bin",
            "LANG": "C.UTF-8", "TERM": "xterm-256color", "COLUMNS": "120", "LINES": "40",
            "COCO_DATA_DIR": str(self.root / "state"), "COCO_LOG_DIR": str(self.root / "logs"),
            "COCO_TMUX_SOCKET": self.socket, "CODEX_BIN": str(self.fake), "CLAUDE_BIN": str(self.fake),
            "COCO_RECORD_DIR": str(self.records),
        }
        self.prefix = self.root / "install prefix"
        self.command = self.prefix / "bin/coco"

    def tearDown(self):
        if shutil.which("tmux"):
            subprocess.run(["tmux", "-L", self.socket, "kill-server"], capture_output=True)
        self.temp.cleanup()

    def run_command(self, args, expected=0, env=None):
        result = subprocess.run([str(x) for x in args], env=env or self.env, cwd=self.home,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def install(self):
        self.run_command([sys.executable, ROOT / "install.py", "--prefix", self.prefix])

    def tmux(self, *args):
        return self.run_command(["tmux", "-L", self.socket, *args]).stdout.strip()

    def await_record(self, slot):
        record = self.records / f"{slot}.json"
        for _ in range(100):
            if record.exists():
                return json.loads(record.read_text())
            time.sleep(0.05)
        self.fail("Agent did not launch for slot " + str(slot))

    def test_install_help_conflicts_and_uninstall(self):
        self.install()
        self.assertEqual(self.command.resolve(), self.prefix / "share/cocopane/monitor/coco")
        self.run_command([self.command, "--help"])
        self.run_command([self.command, "help", "open"])
        self.run_command([self.command, "doctor", "--agent", "codex"])
        self.run_command([self.command, "--version"])
        before = self.command.resolve().read_bytes()
        self.run_command([sys.executable, ROOT / "install.py", "--prefix", self.prefix], expected=2)
        self.assertEqual(self.command.resolve().read_bytes(), before)
        logs = Path(self.env["COCO_LOG_DIR"])
        logs.mkdir()
        (logs / "keep.log").write_text("keep")
        self.run_command([sys.executable, self.prefix / "share/cocopane/install.py", "--prefix", self.prefix, "--uninstall"])
        self.assertFalse(self.command.exists())
        self.assertEqual((logs / "keep.log").read_text(), "keep")
        self.assertFalse((self.home / ".bashrc").exists())

    def test_installer_does_not_replace_an_existing_command(self):
        self.command.parent.mkdir(parents=True)
        self.command.write_text("existing app")
        self.run_command([sys.executable, ROOT / "install.py", "--prefix", self.prefix], expected=2)
        self.assertEqual(self.command.read_text(), "existing app")

    @unittest.skipUnless(shutil.which("tmux"), "tmux required for dashboard integration")
    def test_actual_launch_resize_logs_modes_and_isolation(self):
        self.install()
        first_env = dict(self.env, TEST_AUTH_VALUE="first-session-only")
        self.run_command([self.command, "open", "--detach"], env=first_env)
        first = self.await_record(1)
        args = first["args"]
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)
        rules = json.loads(next(x for x in args if x.startswith("developer_instructions=")).split("=", 1)[1])
        self.assertTrue(rules.startswith("PRESERVE_MY_RULES"))
        self.assertIn('COCO_SLOT="1"', rules)
        self.assertEqual(first["env"]["TEST_AUTH_VALUE"], "first-session-only")
        session = self.tmux("list-sessions", "-F", "#{session_name}").splitlines()[0]
        panes = self.tmux("list-panes", "-t", session, "-F", "#{pane_id}").splitlines()
        self.assertEqual(len(panes), 4)
        self.assertEqual(self.tmux("show-options", "-v", "-t", session, "mouse"), "on")
        self.assertEqual(self.tmux("display-message", "-p", "-t", panes[0], "#{history_limit}"), "200000")
        commands = self.tmux("list-panes", "-t", session, "-F", "#{pane_start_command}")
        self.assertNotIn("first-session-only", commands)
        for width in (200, 100):
            self.tmux("resize-window", "-t", session, "-x", str(width), "-y", "40")
            for _ in range(50):
                widths = list(map(int, self.tmux("list-panes", "-t", session, "-F", "#{pane_width}").splitlines()))
                if widths[1:] == [width * 40 // 100] * 3:
                    break
                time.sleep(0.05)
            self.assertEqual(widths[1:], [width * 40 // 100] * 3)
        job = self.root / "job ' special.log"
        job.write_text("EXACT_CURRENT_LOG\n")
        self.run_command([self.command, "set-log", "--slot", "1", job])
        for _ in range(50):
            capture = self.tmux("capture-pane", "-p", "-t", panes[-1])
            if "EXACT_CURRENT_LOG" in capture:
                break
            time.sleep(0.1)
        self.assertIn("EXACT_CURRENT_LOG", capture)
        self.run_command([self.command, "open", "--detach", "--slot", "1"], expected=1)
        self.run_command([self.command, "open", "--detach", "--continue", "--no-gpu", "--no-usage"])
        second = self.await_record(2)
        self.assertEqual(second["args"][-2:], ["resume", "--last"])
        self.assertIsNone(second["env"]["TEST_AUTH_VALUE"])
        self.run_command([self.command, "claude", "--detach", "--resume", "--no-gpu"])
        third = self.await_record(3)
        self.assertIn("--append-system-prompt", third["args"])
        self.assertNotIn("--bare", third["args"])
        self.assertNotIn("--dangerously-skip-permissions", third["args"])
        self.assertEqual(third["args"][-1], "--resume")
        self.run_command([self.command, "kill", "not-coco"], expected=2)
        self.assertEqual(len(self.tmux("list-sessions", "-F", "#{session_name}").splitlines()), 3)
        self.run_command([self.command, "kill", session])
        self.assertNotIn(session, self.tmux("list-sessions", "-F", "#{session_name}"))

    @unittest.skipUnless(shutil.which("tmux"), "tmux required for concurrent launch")
    def test_simultaneous_launches_choose_different_slots(self):
        self.install()
        processes = [subprocess.Popen([str(self.command), "open", "--detach", "--no-usage", "--no-gpu"],
                                     env=self.env, cwd=self.home, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for _ in range(2)]
        for process in processes:
            out, err = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, out + err)
        self.assertEqual(self.await_record(1)["env"]["COCO_SLOT"], "1")
        self.assertEqual(self.await_record(2)["env"]["COCO_SLOT"], "2")


if __name__ == "__main__":
    unittest.main()
