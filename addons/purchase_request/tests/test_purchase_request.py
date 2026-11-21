from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestPurchaseRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendor = cls.env["res.partner"].create({"name": "Test Vendor"})
        cls.product = cls.env["product.product"].create({
            "name": "Test Product",
            "standard_price": 100.0,
        })

    def _make_request(self, qty=1.0, price=100.0):
        return self.env["purchase.request"].create({
            "vendor_id": self.vendor.id,
            "line_ids": [(0, 0, {
                "product_id": self.product.id,
                "quantity": qty,
                "price_unit": price,
            })],
        })

    def test_total_is_computed(self):
        req = self._make_request(qty=3, price=50)
        self.assertEqual(req.total, 150.0)

    def test_sequence_is_generated(self):
        req = self._make_request()
        self.assertTrue(req.name.startswith("PR/"))

    def test_submit_without_lines_fails(self):
        req = self.env["purchase.request"].create({"vendor_id": self.vendor.id})
        with self.assertRaises(UserError):
            req.action_submit()

    def test_full_workflow_creates_purchase_order(self):
        req = self._make_request(qty=2, price=100)
        req.action_submit()
        self.assertEqual(req.state, "to_approve")
        req.action_approve()
        self.assertEqual(req.state, "approved")
        req.action_create_po()
        self.assertEqual(req.state, "done")
        self.assertTrue(req.purchase_order_id)
        self.assertEqual(req.purchase_order_id.partner_id, self.vendor)
        self.assertEqual(req.purchase_order_id.amount_untaxed, 200.0)

    def test_reject(self):
        req = self._make_request()
        req.action_submit()
        req.action_reject()
        self.assertEqual(req.state, "rejected")

    def test_reset_to_draft_after_reject(self):
        req = self._make_request()
        req.action_submit()
        req.action_reject()
        req.action_draft()
        self.assertEqual(req.state, "draft")

    def test_create_po_requires_vendor(self):
        req = self._make_request()
        req.vendor_id = False
        req.action_submit()
        req.action_approve()
        with self.assertRaises(UserError):
            req.action_create_po()

    def test_large_amount_requires_manager(self):
        req = self._make_request(qty=2, price=1000)
        req.action_submit()
        users_model = type(self.env["res.users"])
        with patch.object(users_model, "has_group", return_value=False):
            with self.assertRaises(UserError):
                req.action_approve()
        # Un manager peut approuver
        with patch.object(users_model, "has_group", return_value=True):
            req.action_approve()
        self.assertEqual(req.state, "approved")

    def test_submit_notifies_managers(self):
        req = self._make_request()
        req.action_submit()
        self.assertTrue(req.activity_ids)

    def test_approve_clears_activities(self):
        req = self._make_request()
        req.action_submit()
        req.action_approve()
        self.assertFalse(req.activity_ids)