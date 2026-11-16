"""Regression tests for the English Consistency/Balance auditors and the
localized (English) report shell.

Mirrors the Chinese auditors one-to-one: same dimensions (assignment
contradiction, party rights imbalance), English keywords/regex only.
Report shell: HTML/Markdown titles and fixed copy follow report.lang;
JSON field names are unchanged.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_engine.auditors import BalanceAuditor, ConsistencyAuditor  # noqa: E402
from compliance_engine.engine import ComplianceEngine  # noqa: E402
from compliance_engine.models import DocType  # noqa: E402
from compliance_engine.report import to_dict, to_html, to_markdown  # noqa: E402

EN_CONTRADICTION = """Service Agreement
1. Price. The total amount is USD 50,000.
2. Term. The contract term is 12 months.
3. Payment. The total amount is USD 60,000.
4. Effective date. The effective date is 1 November 2022.
5. Renewal. The effective date is 1 December 2022.
"""

EN_CONSISTENT = """Service Agreement
1. Price. The total amount is USD 50,000.
2. Term. The contract term is 12 months.
3. Payment. The total amount is USD 50,000.
"""

EN_DEFINED_TERM = """Service Agreement
In this agreement, "ABC" means Alpha Beta Company Limited.
Party A shall pay ABC for the services.
In this agreement, "ABC" means Gamma Delta Trading Co.
"""

EN_IMBALANCED = """Service Agreement
1. Party A may terminate the agreement at any time.
2. Party A shall have the right to adjust the delivery schedule.
3. Party A is entitled to inspect the work at any time.
4. Party B shall deliver the goods by 31 December 2026.
"""

EN_BALANCED = """Service Agreement
1. Party A may terminate the agreement at any time.
2. Party B may terminate the agreement at any time.
3. Party A shall deliver the goods.
4. Party B shall pay the price.
"""

ZH_CONTRADICTION = "服务合同\n第一条 合同期限为12月。\n第二条 合同期限为24月。\n"
ZH_IMBALANCED = (
    "服务合同\n第一条 甲方有权调整交付计划，甲方有权变更验收标准，"
    "甲方有权单方解除合同。\n第二条 乙方应按时交付。\n"
)


class TestEnglishConsistency(unittest.TestCase):
    def test_amount_and_date_contradictions(self):
        findings = ConsistencyAuditor().audit(
            EN_CONTRADICTION, DocType.CONTRACT, lang="en")
        messages = [f.message for f in findings
                    if f.rule_id == "CONSIST-contract"]
        self.assertEqual(len(messages), 2)
        self.assertTrue(any("total amount" in m for m in messages), messages)
        self.assertTrue(any("effective date" in m for m in messages), messages)

    def test_same_value_twice_is_not_a_contradiction(self):
        findings = ConsistencyAuditor().audit(
            EN_CONSISTENT, DocType.CONTRACT, lang="en")
        self.assertEqual(
            [f for f in findings if f.rule_id.startswith("CONSIST-")], [])

    def test_equivalent_forms_are_the_same_value(self):
        text = ("Service Agreement\n"
                "1. Price. The total amount is USD 50,000.\n"
                "2. Payment. The total amount is 50000 USD.\n")
        findings = ConsistencyAuditor().audit(text, DocType.CONTRACT, lang="en")
        self.assertEqual(
            [f for f in findings if f.rule_id.startswith("CONSIST-")], [])

    def test_defined_term_conflict(self):
        findings = ConsistencyAuditor().audit(
            EN_DEFINED_TERM, DocType.CONTRACT, lang="en")
        messages = [f.message for f in findings
                    if f.rule_id == "CONSIST-contract"]
        self.assertEqual(len(messages), 1)
        self.assertIn("ABC", messages[0])

    def test_chinese_consistency_unchanged(self):
        findings = ConsistencyAuditor().audit(ZH_CONTRADICTION, DocType.CONTRACT)
        messages = [f.message for f in findings
                    if f.rule_id == "CONSIST-contract"]
        self.assertEqual(len(messages), 1)
        self.assertIn("合同期限", messages[0])


class TestEnglishBalance(unittest.TestCase):
    def test_imbalance_detected(self):
        findings = BalanceAuditor().audit(
            EN_IMBALANCED, DocType.CONTRACT, lang="en")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "BALANCE-CONTRACT")
        self.assertIn("Party A", findings[0].message)

    def test_balanced_contract_no_finding(self):
        findings = BalanceAuditor().audit(
            EN_BALANCED, DocType.CONTRACT, lang="en")
        self.assertEqual(findings, [])

    def test_balance_only_for_contracts(self):
        findings = BalanceAuditor().audit(
            EN_IMBALANCED, DocType.REGULATION, lang="en")
        self.assertEqual(findings, [])

    def test_chinese_balance_unchanged(self):
        findings = BalanceAuditor().audit(ZH_IMBALANCED, DocType.CONTRACT)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "BALANCE-CONTRACT")
        self.assertIn("甲方", findings[0].message)


class TestEnglishReportShell(unittest.TestCase):
    def test_html_shell_is_english(self):
        report = ComplianceEngine().audit(
            EN_CONTRADICTION, DocType.CONTRACT, lang="en")
        html = to_html(report)
        for s in ("Document Compliance Audit Report", "Verdict",
                  "Findings", "Audit trace", "Overall score"):
            self.assertIn(s, html)
        self.assertIn('<html lang="en">', html)
        for s in ("文书合规审计报告", "问题清单", "审计追溯链", "综合评分", "汇总"):
            self.assertNotIn(s, html)

    def test_markdown_shell_is_english(self):
        report = ComplianceEngine().audit(
            EN_CONTRADICTION, DocType.CONTRACT, lang="en")
        md = to_markdown(report)
        self.assertTrue(md.startswith("# Document Compliance Audit Report"))
        self.assertIn("## Findings", md)
        self.assertIn("## Audit trace", md)
        self.assertIn("Verdict: Fail", md)
        for s in ("文书合规审计报告", "问题清单", "审计追溯链"):
            self.assertNotIn(s, md)

    def test_json_field_names_unchanged(self):
        report = ComplianceEngine().audit(
            EN_CONTRADICTION, DocType.CONTRACT, lang="en")
        d = to_dict(report)
        self.assertEqual(set(d.keys()), {
            "doc_type", "title", "overall_score", "passed", "generated_at",
            "summary", "responsibility", "findings", "trace"})
        self.assertTrue(d["findings"])
        self.assertEqual(set(d["findings"][0].keys()), {
            "rule_id", "category", "severity", "message", "suggestion",
            "location", "snippet"})

    def test_chinese_report_shell_unchanged(self):
        report = ComplianceEngine().audit(ZH_CONTRADICTION, DocType.CONTRACT)
        html = to_html(report)
        for s in ("文书合规审计报告", "判定", "问题清单", "审计追溯链"):
            self.assertIn(s, html)
        md = to_markdown(report)
        self.assertTrue(md.startswith("# 文书合规审计报告"))

    def test_engine_end_to_end_english_findings(self):
        report = ComplianceEngine().audit(
            EN_IMBALANCED, DocType.CONTRACT, lang="en")
        rule_ids = {f.rule_id for f in report.findings}
        self.assertIn("BALANCE-CONTRACT", rule_ids)


if __name__ == "__main__":
    unittest.main()
