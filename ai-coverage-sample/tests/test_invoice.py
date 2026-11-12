import unittest
from decimal import Decimal

from invoice import invoice_total


class InvoiceTests(unittest.TestCase):
    def test_standard_order(self):
        self.assertEqual(invoice_total("100"), Decimal("100.00"))

    def test_small_order_shipping(self):
        self.assertEqual(invoice_total("20"), Decimal("25.00"))

    def test_vip_express_order(self):
        self.assertEqual(invoice_total("100", "vip", "express"), Decimal("95.00"))


if __name__ == "__main__":
    unittest.main()
