"""Regression tests for the stress-test fixes (exit codes, occurrence coverage, rule patterns)."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_engine.engine import ComplianceEngine  # noqa: E402
from compliance_engine.models import DocType  # noqa: E402

ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


class TestKeywordCoverage(unittest.TestCase):
    def test_all_occurrences_reported(self):
        text = "服务合同\n" + "".join(
            f"第{i}条 乙方押金人民币5000元。\n" for i in range(1, 301)
        )
        report = ComplianceEngine().audit(text, DocType.CONTRACT)
        hits = [f for f in report.findings if f.rule_id == "CT-005"]
        self.assertGreaterEqual(len(hits), 200)
        self.assertTrue(any("仅列前 200 处" in f.message for f in hits))

    def test_findings_attach_to_nodes(self):
        text = "服务合同\n第一条 乙方应在通知后及时完成。\n第二条 甲方单方解除且不承担责任。\n"
        report = ComplianceEngine().audit(text, DocType.CONTRACT)
        self.assertGreater(len(report.nodes), 0)
        self.assertGreater(sum(len(n.findings) for n in report.nodes), 0)


class TestRulePatterns(unittest.TestCase):
    def test_percentage_violation_without_threshold_word(self):
        text = "劳动合同\n第一条 乙方违约金为合同总额的50%。\n"
        rules = {f.rule_id for f in ComplianceEngine().audit(text, DocType.CONTRACT).findings}
        self.assertIn("CT-003", rules)

    def test_vague_time_word(self):
        text = "服务合同\n第一条 乙方应及时完成工作。\n"
        rules = {f.rule_id for f in ComplianceEngine().audit(text, DocType.CONTRACT).findings}
        self.assertIn("COM-001", rules)


class TestCliExitCodes(unittest.TestCase):
    def test_missing_file_returns_2(self):
        p = subprocess.run(
            [sys.executable, "-m", "compliance_engine", "audit", "--type", "contract",
             "--input", str(ROOT / "definitely_missing.txt")],
            cwd=str(ROOT), capture_output=True, env=ENV,
        )
        self.assertEqual(p.returncode, 2)

    def test_invalid_utf8_returns_1(self):
        bad = ROOT / "_bad_utf8.tmp"
        bad.write_bytes(b"\xff\xfe\x00\x00bad")
        try:
            p = subprocess.run(
                [sys.executable, "-m", "compliance_engine", "audit", "--type", "contract",
                 "--input", str(bad)],
                cwd=str(ROOT), capture_output=True, env=ENV,
            )
            self.assertEqual(p.returncode, 1)
        finally:
            bad.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
