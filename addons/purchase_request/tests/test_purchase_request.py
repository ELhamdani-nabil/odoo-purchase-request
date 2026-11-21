from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase

MANAGER_GROUP = "purchase_request.group_purchase_request_manager"


class TestPurchaseRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendor = cls.env["res.partner"].create({"name": "Test Vendor"})
        cls.product = cls.env["product.product"].create({
            "name": "Test Product",
            "standard_price": 100.0,
        })
        cls.users_model = type(cls.env["res.users"])

    def _make_request(self, qty=1.0, price=100.0):
        return self.env["purchase.request"].create({
            "vendor_id": self.vendor.id,
            "line_ids": [(0, 0, {
                "product_id": self.product.id,
                "quantity": qty,
                "price_unit": price,
            })],
        })

    # --- Calculs de base -------------------------------------------------
    def test_total_is_computed(self):
        req = self._make_request(qty=3, price=50)
        self.assertEqual(req.total, 150.0)

    def test_sequence_is_generated(self):
        req = self._make_request()
        self.assertTrue(req.name.startswith("PR/"))

    def test_request_date_default(self):
        self.assertTrue(self._make_request().request_date)

    def test_approval_level_computed(self):
        self.assertEqual(self._make_request(1, 1000).approval_level, "user")
        self.assertEqual(self._make_request(1, 1001).approval_level, "manager")
        self.assertEqual(self._make_request(1, 10001).approval_level, "director")

    def test_invalid_quantity_rejected(self):
        with self.assertRaises(ValidationError):
            self._make_request(qty=0)

    def test_department_from_employee(self):
        dept = self.env["hr.department"].create({"name": "Departement Test"})
        user = self.env["res.users"].create({
            "name": "Demandeur Test", "login": "demandeur_test"})
        employee = self.env["hr.employee"].search(
            [("user_id", "=", user.id)], limit=1)
        if employee:
            employee.department_id = dept
        else:
            self.env["hr.employee"].create({
                "name": "Demandeur Test",
                "user_id": user.id,
                "department_id": dept.id,
            })
        req = self.env["purchase.request"].create({
            "requester_id": user.id,
            "vendor_id": self.vendor.id,
            "line_ids": [(0, 0, {
                "product_id": self.product.id, "quantity": 1, "price_unit": 10,
            })],
        })
        self.assertEqual(req.department_id, dept)

    # --- Workflow --------------------------------------------------------
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

    def test_cannot_approve_a_draft(self):
        req = self._make_request()
        with self.assertRaises(UserError):
            req.action_approve()

    def test_approval_traceability(self):
        req = self._make_request()
        req.action_submit()
        req.action_approve()
        self.assertEqual(req.approver_id, self.env.user)
        self.assertTrue(req.approval_date)

    def test_cannot_delete_processed_request(self):
        req = self._make_request()
        req.action_submit()
        req.action_approve()
        with self.assertRaises(UserError):
            req.unlink()
        draft = self._make_request()
        draft.unlink()  # un brouillon peut être supprimé

    # --- Niveaux d'approbation -------------------------------------------
    def test_large_amount_requires_manager(self):
        req = self._make_request(qty=2, price=1000)  # 2 000
        req.action_submit()
        with patch.object(self.users_model, "has_group", return_value=False):
            with self.assertRaises(UserError):
                req.action_approve()
        with patch.object(self.users_model, "has_group", return_value=True):
            req.action_approve()
        self.assertEqual(req.state, "approved")

    def test_manager_can_approve_mid_amount(self):
        req = self._make_request(qty=2, price=1000)  # 2 000
        req.action_submit()
        with patch.object(
                self.users_model, "has_group",
                side_effect=lambda group: group == MANAGER_GROUP):
            req.action_approve()
        self.assertEqual(req.state, "approved")

    def test_very_large_amount_requires_director(self):
        req = self._make_request(qty=3, price=5000)  # 15 000
        req.action_submit()
        with patch.object(
                self.users_model, "has_group",
                side_effect=lambda group: group == MANAGER_GROUP):
            with self.assertRaises(UserError):
                req.action_approve()
        with patch.object(self.users_model, "has_group", return_value=True):
            req.action_approve()
        self.assertEqual(req.state, "approved")

    # --- Notifications ---------------------------------------------------
    def test_submit_notifies_approvers(self):
        req = self._make_request()
        req.action_submit()
        self.assertTrue(req.activity_ids)

    def test_approve_clears_activities(self):
        req = self._make_request()
        req.action_submit()
        req.action_approve()
        self.assertFalse(req.activity_ids)

    # --- Analyse ---------------------------------------------------------
    def test_expenses_grouped_by_vendor(self):
        other_vendor = self.env["res.partner"].create({"name": "Other Vendor"})
        self._make_request(qty=1, price=100)
        self._make_request(qty=2, price=100)
        other = self._make_request(qty=1, price=500)
        other.vendor_id = other_vendor
        requests = self.env["purchase.request"].search([
            ("vendor_id", "in", [self.vendor.id, other_vendor.id]),
        ])
        result = dict(self.env["purchase.request"]._read_group(
            [("id", "in", requests.ids)],
            groupby=["vendor_id"],
            aggregates=["total:sum"],
        ))
        self.assertEqual(result[self.vendor], 300.0)
        self.assertEqual(result[other_vendor], 500.0)