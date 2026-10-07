import importlib.util
from datetime import datetime
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    "codex_status", Path(__file__).with_name("_pane_codex_status.py")
)
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


class UsageDisplayTests(unittest.TestCase):
    def test_weekly_primary_is_not_labeled_five_hours(self):
        lines = status.usage_lines({"rateLimits": {
            "primary": {"windowDurationMins": 10080, "usedPercent": 1},
            "secondary": None,
        }})
        self.assertIn("7天额度：剩余 99% · 已用 1%", lines)
        self.assertNotIn("5小时", "\n".join(lines))

    def test_both_windows_and_multiple_buckets(self):
        lines = status.usage_lines({"rateLimitsByLimitId": {
            "codex": {
                "primary": {"windowDurationMins": 300, "usedPercent": 25},
                "secondary": {"windowDurationMins": 10080, "usedPercent": 40},
            },
            "other": {"primary": {"windowDurationMins": 60, "usedPercent": 100}},
        }})
        for expected in ("5小时额度：剩余 75% · 已用 25%", "7天额度：剩余 60% · 已用 40%", "1小时额度：剩余 0% · 已用 100%"):
            self.assertIn(expected, lines)

    def test_missing_data_does_not_become_unused_quota(self):
        lines = status.usage_lines({"rateLimits": {"primary": {"windowDurationMins": 300}}})
        self.assertIn("5小时额度：暂无数据", lines)
        self.assertNotIn("100%", "\n".join(lines))
        self.assertIn("暂无额度窗口数据", status.usage_lines({}))

    def test_failure_marks_previous_data_as_stale(self):
        lines = status.usage_lines({}, datetime(2026, 10, 7, 12), "读取失败")
        self.assertIn("读取失败", lines)
        self.assertEqual(lines[-1], "更新：12:00:00（旧数据）")

    def test_reset_time_uses_local_timezone(self):
        reset = 1791967696
        lines = status.usage_lines({"rateLimits": {"primary": {
            "usedPercent": 0, "resetsAt": reset,
        }}})
        self.assertIn("  重置：" + datetime.fromtimestamp(reset).strftime("%m-%d %H:%M"), lines)

    def test_terminal_text_fits_and_strips_controls(self):
        self.assertEqual(status.clip("剩余 50%", 6), "剩余 5")
        self.assertNotIn("\x1b", status.clip("plan\x1b[2J", 30))


if __name__ == "__main__":
    unittest.main()
