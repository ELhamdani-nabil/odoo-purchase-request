from odoo import api, fields, models
from odoo.exceptions import UserError

APPROVAL_THRESHOLD = 1000.0
MANAGER_GROUP = "purchase_request.group_purchase_request_manager"


class PurchaseRequest(models.Model):
    _name = "purchase.request"
    _description = "Demande d'achat"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(
        string="Référence", default="Nouveau", readonly=True, copy=False)
    requester_id = fields.Many2one(
        "res.users", string="Demandeur",
        default=lambda self: self.env.user, tracking=True)
    vendor_id = fields.Many2one("res.partner", string="Fournisseur", tracking=True)
    line_ids = fields.One2many("purchase.request.line", "request_id", string="Lignes")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id)
    total = fields.Monetary(
        compute="_compute_total", store=True, currency_field="currency_id")
    state = fields.Selection([
        ("draft", "Brouillon"),
        ("to_approve", "À approuver"),
        ("approved", "Approuvée"),
        ("rejected", "Refusée"),
        ("done", "Commande créée"),
    ], string="Statut", default="draft", tracking=True)
    purchase_order_id = fields.Many2one(
        "purchase.order", string="Bon de commande", readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "Nouveau") == "Nouveau":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "purchase.request") or "Nouveau"
        return super().create(vals_list)

    @api.depends("line_ids.subtotal")
    def _compute_total(self):
        for rec in self:
            rec.total = sum(rec.line_ids.mapped("subtotal"))

    def _notify_managers(self):
        """Crée une activité « à faire » pour chaque manager."""
        managers = self.env["res.users"].search([("share", "=", False)]).filtered(
            lambda u: u.has_group(MANAGER_GROUP))
        for rec in self:
            for manager in managers - rec.requester_id:
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=manager.id,
                    summary="Demande d'achat à approuver : %s" % rec.name,
                )

    def action_submit(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError("Ajoutez au moins une ligne avant de soumettre.")
        self.write({"state": "to_approve"})
        self._notify_managers()

    def action_approve(self):
        is_manager = self.env.user.has_group(MANAGER_GROUP)
        for rec in self:
            if rec.total > APPROVAL_THRESHOLD and not is_manager:
                raise UserError(
                    "Les demandes de plus de %s nécessitent l'approbation d'un manager."
                    % APPROVAL_THRESHOLD)
        self.write({"state": "approved"})
        self.activity_unlink(["mail.mail_activity_data_todo"])

    def action_reject(self):
        self.write({"state": "rejected"})
        self.activity_unlink(["mail.mail_activity_data_todo"])

    def action_draft(self):
        self.write({"state": "draft"})

    def action_create_po(self):
        self.ensure_one()
        if not self.vendor_id:
            raise UserError("Choisissez un fournisseur.")
        po = self.env["purchase.order"].create({
            "partner_id": self.vendor_id.id,
            "order_line": [(0, 0, {
                "product_id": line.product_id.id,
                "product_qty": line.quantity,
                "price_unit": line.price_unit,
            }) for line in self.line_ids],
        })
        self.write({"purchase_order_id": po.id, "state": "done"})
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "res_id": po.id,
            "view_mode": "form",
        }


class PurchaseRequestLine(models.Model):
    _name = "purchase.request.line"
    _description = "Ligne de demande d'achat"

    request_id = fields.Many2one("purchase.request", ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Produit", required=True)
    quantity = fields.Float(string="Quantité", default=1.0)
    price_unit = fields.Float(string="Prix unitaire")
    subtotal = fields.Float(compute="_compute_subtotal", store=True)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.price_unit = self.product_id.standard_price

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit