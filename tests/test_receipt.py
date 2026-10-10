import unittest

from tests.helpers import ServiceTestCase
from vx7khata import receipt


class ReceiptTests(ServiceTestCase):
    def setUp(self):
        super().setUp()
        self.c = self.svc.add_customer("Ram & Sons", "9876543210")

    def html(self, entries, **kw):
        balance = self.svc.customer_balance(self.c.id)
        return receipt.receipt_html(self.c, entries, balance, shop_name="Raj <Store>", **kw)

    def test_payment_receipt(self):
        self.add(self.c.id, "UDHAAR", "01-10-2026", "Rice", amount="1000")
        pay = self.add(self.c.id, "JAMA", "03-10-2026", "Payment received", amount="400", notes="UPI\nref 77")
        html = self.html([pay])
        self.assertIn("PAYMENT RECEIPT", html)
        self.assertIn("Raj &lt;Store&gt;", html)           # shop name is escaped
        self.assertIn("Ram &amp; Sons", html)
        self.assertIn("Payment received", html)
        self.assertIn("₹400.00", html)
        self.assertIn("Balance due", html)
        self.assertIn("₹600.00", html)
        self.assertIn("UPI ref 77", html)                    # notes squeezed to one line
        self.assertNotIn("<script", html)

    def test_entry_with_qty_and_rate_and_multi_entry_title(self):
        a = self.add(self.c.id, "UDHAAR", "01-10-2026", "Sugar", quantity="2.5", rate="40")
        b = self.add(self.c.id, "JAMA", "02-10-2026", "Cash", amount="30")
        html = self.html([a, b])
        self.assertIn("ACCOUNT SLIP", html)
        self.assertIn("2.5 x 40.00", html)
        self.assertIn("₹100.00", html)                        # 2.5 x 40
        self.assertIn("Total Debit (Dr)", html)
        self.assertIn("Total Credit (Cr)", html)

    def test_balance_wording(self):
        t = self.add(self.c.id, "UDHAAR", "01-10-2026", "x", amount="50")
        self.assertIn("Balance due", receipt.receipt_html(self.c, [t], 5000))
        self.assertIn("Advance", receipt.receipt_html(self.c, [t], -5000))
        self.assertIn("settled", receipt.receipt_html(self.c, [t], 0))

    def test_no_fixed_roll_paper_and_font_is_adjustable(self):
        self.assertFalse(hasattr(receipt, "RECEIPT_WIDTH_MM"))
        self.assertIn("font-size:14pt", receipt.receipt_html(self.c, [], 0, font_pt=14))


if __name__ == "__main__":
    unittest.main()
