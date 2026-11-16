"""Regression tests for CT-005 (English deposit rule).

CT-005 used to match the bare word ``deposit`` (``\\bdeposit\\b``), which
mis-flagged non-deposit uses such as the SAG-AFTRA NDA notice clause
"two (2) days after deposit with an overnight courier service" as a
CRITICAL missing-refund-terms finding. The rule now only fires on real
deposit contexts (security/rental deposit, deposit paid/payable, deposit
in the amount of, deposit shall be refunded/returned, deposit of + amount,
pay a/the deposit, deposit amount); courier / mail / bank-account uses of
"deposit" must not trigger it.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compliance_engine.engine import ComplianceEngine  # noqa: E402
from compliance_engine.models import DocType  # noqa: E402


def ct005_findings(text):
    report = ComplianceEngine().audit(text, DocType.CONTRACT, lang="en")
    return [f for f in report.findings if f.rule_id == "CT-005"]


# Courier / mail / bank-account senses of "deposit": must NOT trigger.
COURIER_NOTICE = (
    "Notices shall be effective upon the earliest of: actual receipt; "
    "delivery by hand; two (2) days after deposit with an overnight "
    "courier service; or five (5) days after mailing via first-class "
    "certified U.S. mail."
)
MAIL_DEPOSIT = (
    "Notices shall be effective five (5) days after deposit by mail."
)
BANK_DEPOSIT = (
    "Payment shall be made by deposit into an account designated by Party A."
)

# Real deposit clauses without refund conditions: must still trigger.
SECURITY_DEPOSIT = (
    "Party B shall pay a security deposit of USD 5,000 upon signing."
)
RENTAL_DEPOSIT = "The tenant shall pay a rental deposit of $2,000."
DEPOSIT_PAID = "A deposit paid by the tenant shall be held by the landlord."
DEPOSIT_OF_AMOUNT = (
    "The deposit of $1,000 is due upon execution of this agreement."
)
DEPOSIT_AMOUNT = "The deposit amount is USD 2,000."


class TestCT005Deposit(unittest.TestCase):
    def test_courier_notice_does_not_trigger(self):
        self.assertEqual(ct005_findings(COURIER_NOTICE), [])

    def test_mail_deposit_does_not_trigger(self):
        self.assertEqual(ct005_findings(MAIL_DEPOSIT), [])

    def test_bank_account_deposit_does_not_trigger(self):
        self.assertEqual(ct005_findings(BANK_DEPOSIT), [])

    def test_security_deposit_still_triggers(self):
        findings = ct005_findings(SECURITY_DEPOSIT)
        self.assertTrue(findings)
        self.assertTrue(all(f.severity.name == "CRITICAL" for f in findings))

    def test_rental_deposit_still_triggers(self):
        self.assertTrue(ct005_findings(RENTAL_DEPOSIT))

    def test_deposit_paid_still_triggers(self):
        self.assertTrue(ct005_findings(DEPOSIT_PAID))

    def test_deposit_of_amount_still_triggers(self):
        self.assertTrue(ct005_findings(DEPOSIT_OF_AMOUNT))

    def test_deposit_amount_still_triggers(self):
        self.assertTrue(ct005_findings(DEPOSIT_AMOUNT))


if __name__ == "__main__":
    unittest.main()
