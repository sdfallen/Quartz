import unittest
from models import Line
from pricing import subtotal
from taxes import tax_cents
from service import invoice_total
from formatting import format_money
from cli import render_invoice


class InvoiceTests(unittest.TestCase):
    def test_subtotal(self):
        self.assertEqual(subtotal([Line(199, 3), Line(250, 2)]), 1097)

    def test_empty(self):
        self.assertEqual(invoice_total([]), 0)

    def test_validation(self):
        for line in (Line(-1, 2), Line(10, -1), Line(True, 2), Line(10, 1.5)):
            with self.subTest(line=line), self.assertRaises(ValueError):
                subtotal([line])

    def test_tax_half_up(self):
        self.assertEqual(tax_cents(5, 1000), 1)
        self.assertEqual(tax_cents(4, 1000), 0)
        self.assertEqual(tax_cents(123456789, 2000), 24691358)

    def test_discount_before_tax(self):
        self.assertEqual(invoice_total([Line(1000, 2)], 500, 2000), 1800)

    def test_invalid_discount_or_tax(self):
        for discount, rate in ((-1, 2000), (1001, 2000), (0, -1), (0, 10001), (True, 0)):
            with self.subTest(discount=discount, rate=rate), self.assertRaises(ValueError):
                invoice_total([Line(1000, 1)], discount, rate)

    def test_format(self):
        self.assertEqual(format_money(123456), '1.234,56 TL')
        self.assertEqual(format_money(0), '0,00 TL')

    def test_render(self):
        self.assertEqual(render_invoice([Line(1000, 2)], 500, 2000), 'Toplam: 18,00 TL')
