"""Regression tests for the English rule library (rules/en/*.json).

The English rules mirror the Chinese rules one-to-one (same IDs, same
semantics, English keywords/regex). Language is resolved explicitly
(--lang / lang=) or auto-detected from the CJK/Latin ratio.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_engine.engine import ComplianceEngine  # noqa: E402
from compliance_engine.models import DocType  # noqa: E402
from compliance_engine.rules import RuleEngine, detect_language  # noqa: E402

ENV = dict(os.environ, PYTHONIOENCODING="utf-8")

# Condensed excerpt of the LE02 Signing Process Policy (msg global
# solutions, v3.2, effective 1 Nov 2022): purpose, scope, responsibilities,
# procedure and effective date are all present in English; penalties are
# genuinely absent. Kept in-repo so the test does not depend on /tmp.
LE02_EXCERPT = """Signing Process Policy
1 Document overview
2 Executive Summary
This policy talks about when dual signature is needed and the approvals
needed for various payments, transactions and donations. The main purpose
of this policy is to set out who may sign on behalf of the company.
3 Signing Process Policy
All companies under the umbrella of the holding company, msg global
solutions ag (Switzerland) are required to respect the same principles
for signing documents. This Signing Policy applies to any other companies
in which msg global may become majority owner.
The Executive Board of msg global regularly reviews this Signing Policy
and is responsible for making any revisions or clarifications as warranted.
4 Dual Signatures (Four Eyes Principle)
All contract documents need to be signed by two (2) persons, who are
authorized to represent their respective company. Only in exceptional
circumstances would it be possible for only one of the authorized
representatives to sign a contract on his own, and only within the limits
of their power of attorney and as long as he has obtained the written
approval of the other representative. This principle always ensures that
two persons will have reviewed, read and understood the contracts.
6.2 Approval Matrix for Customer Contracts
The below table shows the Review and Approval Process for Proposal and
Contracts. Amounts above 100,000 EUR require process approval and review
of all relevant parties listed. The Head of Marketing is able to sign any
kind of contract related to Marketing activities if necessary, and the
Legal Department must be notified in a timely manner, etc.
19 Effective Date
This update of the policy will be effective from 01 November 2022.
"""

EN_CONTRACT_SAMPLE = """Service Agreement
1. Parties. This agreement is entered into between Party A and Party B.
2. Subject matter. Party B shall provide software services and deliverables.
3. Price. The total amount payable is USD 50,000. Payment is due within
30 days. The term of this agreement is 12 months, with completion by
31 December 2026.
4. Deposit. Party B shall pay a security deposit of USD 5,000.
5. Liquidated damages. If Party B is in breach, liquidated damages shall
be 50% of the contract amount. Party A has the final right of
interpretation and Party B shall not be liable for any delay. Party B
shall complete the work in a timely manner.
6. Dispute resolution. Any dispute shall be submitted to arbitration.
"""

CHINESE_CONTRACT = "服务合同\n第一条 乙方应在通知后及时完成。\n第二条 乙方押金人民币5000元。\n"


class TestLanguageDetection(unittest.TestCase):
    def test_english_detected(self):
        self.assertEqual(detect_language(LE02_EXCERPT), "en")

    def test_chinese_detected(self):
        self.assertEqual(detect_language(CHINESE_CONTRACT), "zh")

    def test_rule_counts_match(self):
        zh_ids = sorted(r["id"] for r in RuleEngine(lang="zh").list_rules())
        en_ids = sorted(r["id"] for r in RuleEngine(lang="en").list_rules())
        self.assertEqual(len(zh_ids), 14)
        self.assertEqual(len(en_ids), 14)
        self.assertEqual(zh_ids, en_ids)


class TestEnglishRegulationLE02(unittest.TestCase):
    def test_le02_no_longer_scores_10(self):
        report = ComplianceEngine().audit(LE02_EXCERPT, DocType.REGULATION)
        self.assertGreater(report.overall_score, 10)
        self.assertLess(report.overall_score, 100)

    def test_le02_rule_scan_hits(self):
        report = ComplianceEngine().audit(LE02_EXCERPT, DocType.REGULATION)
        rule_hits = [f for f in report.findings
                     if f.rule_id.startswith(("COM-", "RG-", "CT-", "OD-"))]
        self.assertGreater(len(rule_hits), 0)

    def test_le02_five_elements_no_longer_missing(self):
        report = ComplianceEngine().audit(LE02_EXCERPT, DocType.REGULATION)
        missing = [f.message for f in report.findings
                   if f.rule_id.startswith("COMPLETE-")]
        for present in ("Purpose", "Scope", "Responsibilities", "Procedure",
                        "Effective date"):
            self.assertFalse(any(present in m for m in missing),
                             f"{present} wrongly reported missing: {missing}")

    def test_le02_penalties_still_missing(self):
        # The one genuinely absent element must still be caught.
        report = ComplianceEngine().audit(LE02_EXCERPT, DocType.REGULATION)
        missing = [f.message for f in report.findings
                   if f.rule_id.startswith("COMPLETE-")]
        self.assertTrue(any("Penalties" in m for m in missing), missing)

    def test_explicit_lang_en_matches_auto(self):
        auto = ComplianceEngine().audit(LE02_EXCERPT, DocType.REGULATION)
        explicit = ComplianceEngine().audit(LE02_EXCERPT, DocType.REGULATION,
                                            lang="en")
        self.assertEqual(auto.overall_score, explicit.overall_score)
        self.assertEqual({f.message for f in auto.findings},
                         {f.message for f in explicit.findings})


class TestEnglishContract(unittest.TestCase):
    def test_contract_rules_hit(self):
        report = ComplianceEngine().audit(EN_CONTRACT_SAMPLE, DocType.CONTRACT)
        rule_ids = {f.rule_id for f in report.findings}
        self.assertIn("CT-005", rule_ids)  # deposit
        self.assertIn("CT-003", rule_ids)  # liquidated damages 50%
        self.assertIn("COM-001", rule_ids)  # timely
        self.assertIn("CT-001", rule_ids)  # final right of interpretation

    def test_contract_elements_present(self):
        report = ComplianceEngine().audit(EN_CONTRACT_SAMPLE, DocType.CONTRACT)
        missing = [f.message for f in report.findings
                   if f.rule_id.startswith("COMPLETE-")]
        self.assertEqual(missing, [])


class TestChinesePathUnchanged(unittest.TestCase):
    def test_chinese_rules_still_hit(self):
        report = ComplianceEngine().audit(CHINESE_CONTRACT, DocType.CONTRACT)
        rule_ids = {f.rule_id for f in report.findings}
        self.assertIn("COM-001", rule_ids)
        self.assertIn("CT-005", rule_ids)

    def test_chinese_findings_still_chinese(self):
        report = ComplianceEngine().audit(CHINESE_CONTRACT, DocType.CONTRACT)
        self.assertTrue(all("Missing required element" not in f.message
                            for f in report.findings))


class TestCliLang(unittest.TestCase):
    def test_list_rules_en(self):
        p = subprocess.run(
            [sys.executable, "-m", "compliance_engine", "list-rules", "--lang", "en"],
            cwd=str(ROOT), capture_output=True, text=True, env=ENV,
        )
        self.assertEqual(p.returncode, 0)
        self.assertIn("共 14 条规则", p.stdout)


if __name__ == "__main__":
    unittest.main()
