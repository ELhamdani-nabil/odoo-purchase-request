from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

APPROVAL_THRESHOLD = 1000.0   # au-delà : approbation d'un manager
DIRECTOR_THRESHOLD = 10000.0  # au-delà : approbation de la Direction
MANAGER_GROUP = "purchase_request.group_purchase_request_manager"
DIRECTOR_GROUP = "purchase_request.group_purchase_request_director"


def _fmt(amount):
    return "{:,.0f}".format(amount).replace(",", " ")


class PurchaseRequest(models.Model):
    _name = "purchase.request"
    _description = "Demande d'achat"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority desc, id desc"

    name = fields.Char(
        string="Référence", default="Nouveau", readonly=True, copy=False)
    requester_id = fields.Many2one(
        "res.users", string="Demandeur",
        default=lambda self: self.env.user, tracking=True)
    department_id = fields.Many2one(
        "hr.department", string="Département",
        compute="_compute_department", store=True)
    vendor_id = fields.Many2one("res.partner", string="Fournisseur", tracking=True)
    request_date = fields.Date(
        string="Date de la demande",
        default=fields.Date.context_today, tracking=True)
    priority = fields.Selection([
        ("0", "Normale"),
        ("1", "Haute"),
        ("2", "Urgente"),
    ], string="Priorité", default="0")
    description = fields.Text(string="Justification")
    line_ids = fields.One2many(
        "purchase.request.line", "request_id", string="Lignes")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id)
    total = fields.Monetary(
        compute="_compute_total", store=True, currency_field="currency_id")
    approval_level = fields.Selection([
        ("user", "Utilisateur"),
        ("manager", "Manager"),
        ("director", "Direction"),
    ], string="Niveau d'approbation", compute="_compute_approval_level",
        store=True)
    state = fields.Selection([
        ("draft", "Brouillon"),
        ("to_approve", "À approuver"),
        ("approved", "Approuvée"),
        ("rejected", "Refusée"),
        ("done", "Commande créée"),
    ], string="Statut", default="draft", tracking=True,
        group_expand="_expand_states")
    approver_id = fields.Many2one(
        "res.users", string="Approuvé par", readonly=True, copy=False)
    approval_date = fields.Datetime(
        string="Date d'approbation", readonly=True, copy=False)
    purchase_order_id = fields.Many2one(
        "purchase.order", string="Bon de commande", readonly=True, copy=False)

    # ------------------------------------------------------------------
    # Kanban : toutes les colonnes, dans l'ordre du workflow
    # ------------------------------------------------------------------
    @api.model
    def _expand_states(self, states, domain):
        return [key for key, _label in self._fields["state"].selection]

    # ------------------------------------------------------------------
    # Création, calculs, suppression
    # ------------------------------------------------------------------
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

    @api.depends("total")
    def _compute_approval_level(self):
        for rec in self:
            if rec.total > DIRECTOR_THRESHOLD:
                rec.approval_level = "director"
            elif rec.total > APPROVAL_THRESHOLD:
                rec.approval_level = "manager"
            else:
                rec.approval_level = "user"

    @api.depends("requester_id")
    def _compute_department(self):
        employees = self.env["hr.employee"].sudo().search(
            [("user_id", "in", self.requester_id.ids)])
        department_by_user = {
            emp.user_id.id: emp.department_id for emp in employees}
        for rec in self:
            rec.department_id = department_by_user.get(
                rec.requester_id.id, False)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_processed(self):
        if any(rec.state not in ("draft", "rejected") for rec in self):
            raise UserError(
                "Seules les demandes en brouillon ou refusées "
                "peuvent être supprimées.")

    # ------------------------------------------------------------------
    # Outils
    # ------------------------------------------------------------------
    def _ensure_state(self, *states):
        labels = dict(self._fields["state"].selection)
        for rec in self:
            if rec.state not in states:
                raise UserError(
                    "Action impossible : la demande %s est à l'état « %s »."
                    % (rec.name, labels[rec.state]))

    def _notify_approvers(self):
        """Crée une activité « à faire » pour les approbateurs concernés :
        la Direction au-delà de 10 000, les managers sinon."""
        users = self.env["res.users"].search([("share", "=", False)])
        for rec in self:
            group = (DIRECTOR_GROUP if rec.approval_level == "director"
                     else MANAGER_GROUP)
            approvers = users.filtered(lambda u: u.has_group(group))
            for approver in approvers - rec.requester_id:
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=approver.id,
                    summary="Demande d'achat à approuver : %s" % rec.name,
                )

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_submit(self):
        self._ensure_state("draft")
        for rec in self:
            if not rec.line_ids:
                raise UserError("Ajoutez au moins une ligne avant de soumettre.")
        self.write({"state": "to_approve"})
        self._notify_approvers()

    def action_approve(self):
        self._ensure_state("to_approve")
        user = self.env.user
        for rec in self:
            if rec.approval_level == "director" and not user.has_group(
                    DIRECTOR_GROUP):
                raise UserError(
                    "Les demandes de plus de %s nécessitent l'approbation "
                    "de la Direction." % _fmt(DIRECTOR_THRESHOLD))
            if rec.approval_level == "manager" and not user.has_group(
                    MANAGER_GROUP):
                raise UserError(
                    "Les demandes de plus de %s nécessitent l'approbation "
                    "d'un manager." % _fmt(APPROVAL_THRESHOLD))
        self.write({
            "state": "approved",
            "approver_id": user.id,
            "approval_date": fields.Datetime.now(),
        })
        self.activity_unlink(["mail.mail_activity_data_todo"])

    def action_reject(self):
        self._ensure_state("to_approve")
        self.write({"state": "rejected"})
        self.activity_unlink(["mail.mail_activity_data_todo"])

    def action_draft(self):
        self._ensure_state("rejected")
        self.write({"state": "draft"})

    def action_create_po(self):
        self.ensure_one()
        self._ensure_state("approved")
        if not (self.env.su or self.env.user.has_group(MANAGER_GROUP)):
            raise UserError(
                "Seul un manager peut créer le bon de commande.")
        if not self.vendor_id:
            raise UserError("Choisissez un fournisseur.")
        po = self.env["purchase.order"].sudo().create({
            "partner_id": self.vendor_id.id,
            "order_line": [(0, 0, {
                "product_id": line.product_id.id,
                "product_qty": line.quantity,
                "price_unit": line.price_unit,
            }) for line in self.line_ids],
        })
        self.write({"purchase_order_id": po.id, "state": "done"})
        return self.action_view_purchase_order()

    def action_view_purchase_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "res_id": self.purchase_order_id.id,
            "view_mode": "form",
        }


class PurchaseRequestLine(models.Model):
    _name = "purchase.request.line"
    _description = "Ligne de demande d'achat"

    request_id = fields.Many2one("purchase.request", ondelete="cascade")
    product_id = fields.Many2one(
        "product.product", string="Produit", required=True)
    quantity = fields.Float(string="Quantité", default=1.0)
    price_unit = fields.Float(string="Prix unitaire")
    subtotal = fields.Float(
        string="Sous-total", compute="_compute_subtotal", store=True)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.price_unit = self.product_id.standard_price

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit

    @api.constrains("quantity", "price_unit")
    def _check_values(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(
                    "La quantité doit être strictement positive.")
            if line.price_unit < 0:
                raise ValidationError(
                    "Le prix unitaire ne peut pas être négatif.")