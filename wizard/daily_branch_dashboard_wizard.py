from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


PRODUCT_GROUPS = [
    ("chicken", "Chicken"),
    ("beef", "Beef"),
    ("bone", "Bone"),
    ("pig", "Pig"),
    ("masala", "Masala"),
]

PRODUCT_KEYWORDS = {
    "chicken": ("chicken",),
    "beef": ("beef",),
    "bone": ("bone",),
    "pig": ("pig", "pork"),
    "masala": ("masala",),
}

BANK_KEYWORDS = ("bank", "upi", "card", "online", "transfer", "neft", "rtgs", "imps")
CASH_KEYWORDS = ("cash",)


class WesprimeDailyBranchDashboard(models.TransientModel):
    _name = "wesprime.daily.branch.dashboard"
    _description = "Daily Branch Control Dashboard"

    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    branch_ids = fields.Many2many(
        "wesprime.branch.ref",
        "war_dbd_branch_rel",
        "dashboard_id",
        "branch_id",
        string="Branches",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True)
    journal_ids = fields.Many2many(
        "account.journal",
        "war_dbd_journal_rel",
        "dashboard_id",
        "journal_id",
        string="Journals",
        domain="[('company_id', '=', company_id)]",
    )
    product_category_ids = fields.Many2many(
        "product.category",
        "war_dbd_categ_rel",
        "dashboard_id",
        "category_id",
        string="Product Categories",
    )
    partner_ids = fields.Many2many(
        "res.partner",
        "war_dbd_partner_rel",
        "dashboard_id",
        "partner_id",
        string="Partners",
    )
    branch_note = fields.Char(readonly=True)
    stock_note = fields.Char(readonly=True)
    summary_line_ids = fields.One2many(
        "wesprime.daily.branch.summary.line",
        "dashboard_id",
        string="Summary",
    )
    sales_line_ids = fields.One2many(
        "wesprime.daily.branch.sales.line",
        "dashboard_id",
        string="Sales Summary",
    )
    payment_line_ids = fields.One2many(
        "wesprime.daily.branch.payment.line",
        "dashboard_id",
        string="Payment Split",
    )
    cash_line_ids = fields.One2many(
        "wesprime.daily.branch.cash.line",
        "dashboard_id",
        string="Cash Control",
    )
    bank_line_ids = fields.One2many(
        "wesprime.daily.branch.bank.line",
        "dashboard_id",
        string="Bank Control",
    )
    credit_line_ids = fields.One2many(
        "wesprime.daily.branch.credit.line",
        "dashboard_id",
        string="Credit Control",
    )
    inventory_line_ids = fields.One2many(
        "wesprime.daily.branch.inventory.line",
        "dashboard_id",
        string="Inventory Snapshot",
    )

    @api.model_create_multi
    def create(self, vals_list):
        dashboards = super().create(vals_list)
        dashboards._refresh_dashboard_lines()
        return dashboards

    @api.model
    def action_open_dashboard(self):
        dashboard = self.create(
            {
                "company_id": self.env.company.id,
                "date_from": fields.Date.context_today(self),
                "date_to": fields.Date.context_today(self),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Daily Branch Control Dashboard"),
            "res_model": self._name,
            "view_mode": "form",
            "view_id": self.env.ref("wesprime_account_reports.view_war_branch_dash_form").id,
            "res_id": dashboard.id,
            "target": "current",
        }

    def _validate_period(self):
        self.ensure_one()
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise UserError(_("Date From cannot be after Date To."))

    def _date_range(self):
        self.ensure_one()
        self._validate_period()
        day = self.date_from
        dates = []
        while day <= self.date_to:
            dates.append(day)
            day += timedelta(days=1)
        return dates

    def _model_available(self, model_name):
        return model_name in self.env.registry

    def _branch_source_model(self):
        for model_name in ("res.branch", "res.company.branch", "company.branch", "account.branch"):
            if self._model_available(model_name):
                return model_name
        return False

    def _company_domain(self, model_name):
        model = self.env[model_name]
        if "company_id" in model._fields:
            return ["|", ("company_id", "=", False), ("company_id", "=", self.company_id.id)]
        return []

    def _branch_ref_model(self):
        return self.env["wesprime.branch.ref"].sudo()

    def _make_branch_ref(self, record, label_prefix=None):
        company = getattr(record, "company_id", False) or self.company_id
        name = record.display_name
        if label_prefix:
            name = "%s: %s" % (label_prefix, name)
        return self._branch_ref_model().get_or_create_ref(record._name, record.id, name, company)

    def _company_branch_ref(self):
        return self._branch_ref_model().get_or_create_ref(
            "res.company",
            self.company_id.id,
            self.company_id.display_name,
            self.company_id,
        )

    def _journal_branch_ref(self, journal):
        if not journal:
            return self._company_branch_ref()
        return self._branch_ref_model().get_or_create_ref(
            "account.journal",
            journal.id,
            _("Journal: %s") % (journal.display_name,),
            journal.company_id or self.company_id,
        )

    def _sync_available_branch_refs(self):
        self.ensure_one()
        self._company_branch_ref()
        branch_model = self._branch_source_model()
        found_real_branches = False
        if branch_model:
            branches = self.env[branch_model].sudo().search(self._company_domain(branch_model), limit=500)
            for branch in branches:
                self._make_branch_ref(branch)
                found_real_branches = True

        journals = self.env["account.journal"].search([("company_id", "=", self.company_id.id)])
        for journal in journals:
            self._journal_branch_ref(journal)

        if self._model_available("account.analytic.account"):
            analytics = self.env["account.analytic.account"].sudo().search(
                self._company_domain("account.analytic.account"),
                limit=500,
            )
            for analytic in analytics:
                self._make_branch_ref(analytic, _("Analytic"))

        if found_real_branches:
            self.branch_note = _("Branch model detected: %s. Untagged entries fall back to journal or company.") % branch_model
        else:
            self.branch_note = _(
                "No branch model detected. Grouping falls back to analytic account, journal, then company."
            )

    def _direct_branch_ref(self, record):
        if not record:
            return False
        branch_model = self._branch_source_model()
        for field_name in ("branch_id", "x_branch_id", "operating_unit_id"):
            field = record._fields.get(field_name)
            if not field or field.type != "many2one":
                continue
            if branch_model and field.comodel_name != branch_model and "branch" not in field.comodel_name:
                continue
            value = record[field_name]
            if value:
                return self._make_branch_ref(value)
        return False

    def _analytic_branch_ref(self, record):
        if not record or not self._model_available("account.analytic.account"):
            return False
        if "analytic_distribution" not in record._fields:
            return False
        distribution = record.analytic_distribution or {}
        analytic_ids = []
        if isinstance(distribution, dict):
            for key in distribution:
                for part in str(key).split(","):
                    if part.isdigit():
                        analytic_ids.append(int(part))
        analytic = self.env["account.analytic.account"].sudo().browse(analytic_ids[:1]).exists()
        if analytic:
            return self._make_branch_ref(analytic, _("Analytic"))
        return False

    def _branch_ref_for_line(self, line):
        direct = self._direct_branch_ref(line)
        if direct:
            return direct
        if getattr(line, "move_id", False):
            direct = self._direct_branch_ref(line.move_id)
            if direct:
                return direct
        if getattr(line, "journal_id", False):
            direct = self._direct_branch_ref(line.journal_id)
            if direct:
                return direct
        analytic = self._analytic_branch_ref(line)
        if analytic:
            return analytic
        if getattr(line, "journal_id", False):
            return self._journal_branch_ref(line.journal_id)
        return self._company_branch_ref()

    def _branch_ref_for_move(self, move):
        direct = self._direct_branch_ref(move)
        if direct:
            return direct
        if getattr(move, "journal_id", False):
            direct = self._direct_branch_ref(move.journal_id)
            if direct:
                return direct
            return self._journal_branch_ref(move.journal_id)
        return self._company_branch_ref()

    def _branch_ref_for_payment(self, payment):
        direct = self._direct_branch_ref(payment)
        if direct:
            return direct
        if getattr(payment, "journal_id", False):
            direct = self._direct_branch_ref(payment.journal_id)
            if direct:
                return direct
            return self._journal_branch_ref(payment.journal_id)
        return self._company_branch_ref()

    def _branch_ref_for_stock_move(self, move):
        direct = self._direct_branch_ref(move)
        if direct:
            return direct
        if getattr(move, "picking_id", False):
            direct = self._direct_branch_ref(move.picking_id)
            if direct:
                return direct
        if getattr(move, "location_id", False):
            direct = self._direct_branch_ref(move.location_id)
            if direct:
                return direct
        if getattr(move, "location_dest_id", False):
            direct = self._direct_branch_ref(move.location_dest_id)
            if direct:
                return direct
        return self._company_branch_ref()

    def _selected_branch_keys(self):
        self.ensure_one()
        return {(branch.source_model, branch.source_res_id) for branch in self.branch_ids}

    def _branch_allowed(self, branch_ref, selected_keys):
        return not selected_keys or (branch_ref.source_model, branch_ref.source_res_id) in selected_keys

    def _product_group(self, product, fallback_text=""):
        text_parts = [fallback_text or ""]
        if product:
            text_parts.extend(
                [
                    product.display_name or "",
                    product.name or "",
                    product.default_code or "",
                    product.categ_id.display_name or "",
                    product.categ_id.complete_name or "",
                ]
            )
        haystack = " ".join(text_parts).lower()
        for group_key, keywords in PRODUCT_KEYWORDS.items():
            if any(keyword in haystack for keyword in keywords):
                return group_key
        return False

    def _line_subtotal(self, line):
        if "price_subtotal" in line._fields:
            return line.price_subtotal or 0.0
        return -line.balance

    def _journal_text(self, journal, extra=""):
        values = [extra or ""]
        if journal:
            values.extend([journal.name or "", journal.display_name or "", journal.code or "", journal.type or ""])
        return " ".join(values).lower()

    def _is_cash_journal(self, journal, extra=""):
        text = self._journal_text(journal, extra)
        return (journal and journal.type == "cash") or any(keyword in text for keyword in CASH_KEYWORDS)

    def _is_bank_journal(self, journal, extra=""):
        text = self._journal_text(journal, extra)
        return (journal and journal.type == "bank") or any(keyword in text for keyword in BANK_KEYWORDS)

    def _base_invoice_line_domain(self, move_types):
        domain = [
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("move_id.move_type", "in", move_types),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("product_id", "!=", False),
            ("display_type", "not in", ("line_section", "line_note")),
        ]
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        if self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))
        if self.product_category_ids:
            domain.append(("product_id.categ_id", "child_of", self.product_category_ids.ids))
        return domain

    def _base_move_domain(self, move_types):
        domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "=", "posted"),
            ("move_type", "in", move_types),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        if self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))
        if self.product_category_ids:
            domain.append(("invoice_line_ids.product_id.categ_id", "child_of", self.product_category_ids.ids))
        return domain

    def _empty_payment_bucket(self):
        return {"cash_sales": 0.0, "bank_sales": 0.0, "credit_sales": 0.0}

    def _empty_credit_bucket(self):
        return {
            "new_credit": 0.0,
            "total_outstanding": 0.0,
            "overdue_amount": 0.0,
            "overdue_partner_ids": set(),
            "overdue_names": set(),
        }

    def _ensure_branch_day(self, branch_days, branch_ref, day):
        branch_days[(branch_ref.id, day)] = branch_ref

    def _collect_sales(self, data):
        selected_keys = data["selected_keys"]
        line_model = self.env["account.move.line"]
        invoice_lines = line_model.search(self._base_invoice_line_domain(("out_invoice", "out_refund")))
        for line in invoice_lines:
            group_key = self._product_group(line.product_id, line.name)
            if not group_key:
                continue
            branch_ref = self._branch_ref_for_line(line)
            if not self._branch_allowed(branch_ref, selected_keys):
                continue
            day = line.date
            sign = -1.0 if line.move_id.move_type == "out_refund" else 1.0
            key = (branch_ref.id, day, group_key)
            data["sales"][key]["quantity"] += (line.quantity or 0.0) * sign
            data["sales"][key]["value"] += self._line_subtotal(line) * sign
            data["sales_qty"][(branch_ref.id, day, group_key)] += (line.quantity or 0.0) * sign
            self._ensure_branch_day(data["branch_days"], branch_ref, day)

        entry_domain = self._base_invoice_line_domain(("entry",))
        entry_lines = line_model.search(entry_domain)
        for line in entry_lines:
            if not self.journal_ids and not (
                line.journal_id.type == "sale"
                or "sale" in (line.journal_id.name or "").lower()
                or "pos" in (line.journal_id.name or "").lower()
            ):
                continue
            group_key = self._product_group(line.product_id, line.name)
            if not group_key:
                continue
            branch_ref = self._branch_ref_for_line(line)
            if not self._branch_allowed(branch_ref, selected_keys):
                continue
            day = line.date
            key = (branch_ref.id, day, group_key)
            value = -line.balance
            data["sales"][key]["quantity"] += line.quantity or 0.0
            data["sales"][key]["value"] += value
            data["sales_qty"][key] += line.quantity or 0.0
            self._ensure_branch_day(data["branch_days"], branch_ref, day)

    def _collect_payments(self, data):
        if not self._model_available("account.payment"):
            return
        payment_model = self.env["account.payment"]
        domain = [
            ("company_id", "=", self.company_id.id),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]
        if "state" in payment_model._fields:
            domain.append(("state", "not in", ("draft", "cancel", "cancelled", "canceled", "rejected")))
        if "payment_type" in payment_model._fields:
            domain.append(("payment_type", "=", "inbound"))
        if "partner_type" in payment_model._fields:
            domain.append(("partner_type", "=", "customer"))
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        if self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))

        for payment in payment_model.search(domain):
            branch_ref = self._branch_ref_for_payment(payment)
            if not self._branch_allowed(branch_ref, data["selected_keys"]):
                continue
            extra = " ".join(
                [
                    getattr(payment, "name", "") or "",
                    getattr(payment, "ref", "") or "",
                    payment.payment_method_line_id.display_name
                    if "payment_method_line_id" in payment._fields and payment.payment_method_line_id
                    else "",
                ]
            )
            amount = payment.amount or 0.0
            bucket = data["payments"][(branch_ref.id, payment.date)]
            # Payments are classified by the receiving journal/method on the payment date.
            if self._is_cash_journal(payment.journal_id, extra):
                bucket["cash_sales"] += amount
            elif self._is_bank_journal(payment.journal_id, extra):
                bucket["bank_sales"] += amount
            self._ensure_branch_day(data["branch_days"], branch_ref, payment.date)

    def _collect_credit_sales(self, data):
        moves = self.env["account.move"].search(self._base_move_domain(("out_invoice",)))
        for move in moves:
            residual = move.amount_residual or 0.0
            if residual <= 0.0:
                continue
            branch_ref = self._branch_ref_for_move(move)
            if not self._branch_allowed(branch_ref, data["selected_keys"]):
                continue
            day = move.date
            # Credit sales are treated as the still-unpaid balance of invoices dated in the period.
            data["payments"][(branch_ref.id, day)]["credit_sales"] += residual
            data["credit"][(branch_ref.id, day)]["new_credit"] += residual
            self._ensure_branch_day(data["branch_days"], branch_ref, day)

    def _collect_expenses(self, data):
        domain = [
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("account_id.account_type", "in", ("expense", "expense_depreciation", "expense_direct_cost")),
        ]
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        if self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))
        for line in self.env["account.move.line"].search(domain):
            if not self._is_cash_journal(line.journal_id):
                continue
            branch_ref = self._branch_ref_for_line(line)
            if not self._branch_allowed(branch_ref, data["selected_keys"]):
                continue
            data["expenses"][(branch_ref.id, line.date)] += line.debit or abs(line.balance)
            self._ensure_branch_day(data["branch_days"], branch_ref, line.date)

    def _collect_credit_control(self, data):
        date_list = data["date_list"]
        domain = [
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("date", "<=", self.date_to),
            ("account_id.account_type", "=", "asset_receivable"),
            ("reconciled", "=", False),
        ]
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        if self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))
        receivable_lines = self.env["account.move.line"].search(domain)
        for line in receivable_lines:
            residual = line.amount_residual or 0.0
            if residual <= 0.0:
                continue
            branch_ref = self._branch_ref_for_line(line)
            if not self._branch_allowed(branch_ref, data["selected_keys"]):
                continue
            maturity_date = line.date_maturity or line.date
            for day in date_list:
                if line.date > day:
                    continue
                bucket = data["credit"][(branch_ref.id, day)]
                bucket["total_outstanding"] += residual
                if maturity_date and maturity_date < day:
                    bucket["overdue_amount"] += residual
                    if line.partner_id:
                        bucket["overdue_partner_ids"].add(line.partner_id.id)
                        bucket["overdue_names"].add(line.partner_id.display_name)
                self._ensure_branch_day(data["branch_days"], branch_ref, day)

    def _stock_move_qty(self, move):
        for field_name in ("quantity", "product_uom_qty"):
            if field_name in move._fields:
                return move[field_name] or 0.0
        return 0.0

    def _stock_direction(self, move):
        source_usage = move.location_id.usage if getattr(move, "location_id", False) else ""
        dest_usage = move.location_dest_id.usage if getattr(move, "location_dest_id", False) else ""
        picking_code = move.picking_type_id.code if getattr(move, "picking_type_id", False) else ""
        internal_usages = ("internal", "transit")
        if picking_code == "incoming" or (dest_usage in internal_usages and source_usage not in internal_usages):
            return "received"
        if picking_code == "outgoing" or (source_usage in internal_usages and dest_usage == "customer"):
            return "sold"
        return False

    def _collect_inventory(self, data):
        if not self._model_available("stock.move"):
            self.stock_note = _("Stock module is not installed. Inventory snapshot is shown as zero.")
            return

        self.stock_note = _("Inventory is estimated from done stock moves; invoice quantities fill missing sold rows.")
        domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "=", "done"),
            ("date", "<", fields.Datetime.to_datetime(self.date_to + timedelta(days=1))),
            ("product_id", "!=", False),
        ]
        if self.product_category_ids:
            domain.append(("product_id.categ_id", "child_of", self.product_category_ids.ids))

        for move in self.env["stock.move"].search(domain):
            group_key = self._product_group(move.product_id, getattr(move, "name", ""))
            if not group_key:
                continue
            direction = self._stock_direction(move)
            if not direction:
                continue
            branch_ref = self._branch_ref_for_stock_move(move)
            if not self._branch_allowed(branch_ref, data["selected_keys"]):
                continue
            move_day = fields.Date.to_date(move.date)
            qty = self._stock_move_qty(move)
            if move_day < self.date_from:
                sign = 1.0 if direction == "received" else -1.0
                data["opening_stock"][(branch_ref.id, group_key)] += qty * sign
                continue
            if move_day > self.date_to:
                continue
            key = (branch_ref.id, move_day, group_key)
            data["inventory_activity"][key].add(direction)
            if direction == "received":
                data["inventory_received"][key] += qty
            elif direction == "sold":
                data["inventory_sold"][key] += qty
            self._ensure_branch_day(data["branch_days"], branch_ref, move_day)

    def _prepare_empty_selected_days(self, data):
        date_list = data["date_list"]
        if self.branch_ids:
            for branch_ref in self.branch_ids:
                for day in date_list:
                    self._ensure_branch_day(data["branch_days"], branch_ref, day)
        if not data["branch_days"]:
            fallback = self._company_branch_ref()
            for day in date_list:
                self._ensure_branch_day(data["branch_days"], fallback, day)

    def _get_or_create_cash_control(self, branch_ref, day, cash_sales, expenses, bank_sales):
        Control = self.env["wesprime.branch.cash.control"]
        domain = [
            ("company_id", "=", self.company_id.id),
            ("branch_ref_id", "=", branch_ref.id),
            ("date", "=", day),
        ]
        control = Control.search(domain, limit=1)
        vals = {
            "cash_sales_system": cash_sales,
            "expenses_system": expenses,
            "bank_sales_system": bank_sales,
        }
        if control:
            control.write(vals)
            return control

        previous = Control.search(
            [
                ("company_id", "=", self.company_id.id),
                ("branch_ref_id", "=", branch_ref.id),
                ("date", "<", day),
            ],
            order="date desc, id desc",
            limit=1,
        )
        opening_cash = previous.actual_closing_cash or previous.closing_cash_expected if previous else 0.0
        vals.update(
            {
                "company_id": self.company_id.id,
                "branch_ref_id": branch_ref.id,
                "date": day,
                "opening_cash": opening_cash,
            }
        )
        return Control.create(vals)

    def _build_dashboard_data(self):
        self.ensure_one()
        self._sync_available_branch_refs()
        data = {
            "date_list": self._date_range(),
            "selected_keys": self._selected_branch_keys(),
            "branch_days": {},
            "sales": defaultdict(lambda: {"quantity": 0.0, "value": 0.0}),
            "sales_qty": defaultdict(float),
            "payments": defaultdict(self._empty_payment_bucket),
            "expenses": defaultdict(float),
            "credit": defaultdict(self._empty_credit_bucket),
            "opening_stock": defaultdict(float),
            "inventory_received": defaultdict(float),
            "inventory_sold": defaultdict(float),
            "inventory_activity": defaultdict(set),
            "cash_controls": {},
        }
        self._collect_sales(data)
        self._collect_payments(data)
        self._collect_credit_sales(data)
        self._collect_expenses(data)
        self._collect_credit_control(data)
        self._collect_inventory(data)
        self._prepare_empty_selected_days(data)

        for (branch_ref_id, day), branch_ref in data["branch_days"].items():
            payment_bucket = data["payments"][(branch_ref_id, day)]
            control = self._get_or_create_cash_control(
                branch_ref,
                day,
                payment_bucket["cash_sales"],
                data["expenses"][(branch_ref_id, day)],
                payment_bucket["bank_sales"],
            )
            data["cash_controls"][(branch_ref_id, day)] = control
        return data

    def _clear_lines(self):
        self.summary_line_ids.unlink()
        self.sales_line_ids.unlink()
        self.payment_line_ids.unlink()
        self.cash_line_ids.unlink()
        self.bank_line_ids.unlink()
        self.credit_line_ids.unlink()
        self.inventory_line_ids.unlink()

    def _inventory_values_for(self, data, branch_ref_id, day, group_key, opening):
        key = (branch_ref_id, day, group_key)
        received = data["inventory_received"][key]
        sold = data["inventory_sold"][key]
        note = ""
        if not self._model_available("stock.move"):
            note = _("Stock module is not installed.")
        elif "sold" not in data["inventory_activity"][key] and data["sales_qty"][key]:
            sold = data["sales_qty"][key]
            note = _("Sold quantity from invoices.")
        closing = opening + received - sold
        return opening, received, sold, closing, note

    def _create_dashboard_lines(self, data):
        summary_vals = []
        sales_vals = []
        payment_vals = []
        cash_vals = []
        bank_vals = []
        credit_vals = []
        inventory_vals = []

        branch_day_items = sorted(
            data["branch_days"].items(),
            key=lambda item: (item[1].name or "", item[0][1], item[0][0]),
        )
        running_stock = defaultdict(float)
        for (branch_ref_id, day), branch_ref in branch_day_items:
            payment_bucket = data["payments"][(branch_ref_id, day)]
            credit_bucket = data["credit"][(branch_ref_id, day)]
            control = data["cash_controls"][(branch_ref_id, day)]
            total_qty = 0.0
            total_value = 0.0
            for group_key, group_label in PRODUCT_GROUPS:
                sales_bucket = data["sales"][(branch_ref_id, day, group_key)]
                total_qty += sales_bucket["quantity"]
                total_value += sales_bucket["value"]
                sales_vals.append(
                    {
                        "dashboard_id": self.id,
                        "branch_ref_id": branch_ref_id,
                        "date": day,
                        "product_group": group_key,
                        "quantity": sales_bucket["quantity"],
                        "value": sales_bucket["value"],
                        "currency_id": self.currency_id.id,
                    }
                )

                opening_key = (branch_ref_id, group_key)
                if opening_key not in running_stock:
                    running_stock[opening_key] = data["opening_stock"][opening_key]
                opening, received, sold, closing, note = self._inventory_values_for(
                    data,
                    branch_ref_id,
                    day,
                    group_key,
                    running_stock[opening_key],
                )
                running_stock[opening_key] = closing
                inventory_vals.append(
                    {
                        "dashboard_id": self.id,
                        "branch_ref_id": branch_ref_id,
                        "date": day,
                        "product_group": group_key,
                        "opening_stock": opening,
                        "received": received,
                        "sold": sold,
                        "closing_stock": closing,
                        "note": note,
                    }
                )

            summary_vals.append(
                {
                    "dashboard_id": self.id,
                    "branch_ref_id": branch_ref_id,
                    "date": day,
                    "sales_quantity": total_qty,
                    "sales_value": total_value,
                    "cash_sales": payment_bucket["cash_sales"],
                    "bank_sales": payment_bucket["bank_sales"],
                    "credit_sales": payment_bucket["credit_sales"],
                    "cash_difference": control.difference,
                    "new_credit": credit_bucket["new_credit"],
                    "total_outstanding": credit_bucket["total_outstanding"],
                    "overdue_customer_count": len(credit_bucket["overdue_partner_ids"]),
                    "currency_id": self.currency_id.id,
                }
            )
            payment_vals.append(
                {
                    "dashboard_id": self.id,
                    "branch_ref_id": branch_ref_id,
                    "date": day,
                    "cash_sales": payment_bucket["cash_sales"],
                    "bank_sales": payment_bucket["bank_sales"],
                    "credit_sales": payment_bucket["credit_sales"],
                    "currency_id": self.currency_id.id,
                }
            )
            cash_vals.append(
                {
                    "dashboard_id": self.id,
                    "branch_ref_id": branch_ref_id,
                    "date": day,
                    "cash_control_id": control.id,
                    "opening_cash": control.opening_cash,
                    "cash_sales_system": control.cash_sales_system,
                    "expenses_system": control.expenses_system,
                    "closing_cash_expected": control.closing_cash_expected,
                    "actual_closing_cash": control.actual_closing_cash,
                    "difference": control.difference,
                    "currency_id": self.currency_id.id,
                }
            )
            bank_vals.append(
                {
                    "dashboard_id": self.id,
                    "branch_ref_id": branch_ref_id,
                    "date": day,
                    "cash_control_id": control.id,
                    "bank_sales_system": control.bank_sales_system,
                    "bank_statement_total": control.bank_statement_total,
                    "bank_difference": control.bank_difference,
                    "currency_id": self.currency_id.id,
                }
            )
            credit_vals.append(
                {
                    "dashboard_id": self.id,
                    "branch_ref_id": branch_ref_id,
                    "date": day,
                    "new_credit": credit_bucket["new_credit"],
                    "total_outstanding": credit_bucket["total_outstanding"],
                    "overdue_amount": credit_bucket["overdue_amount"],
                    "overdue_customer_count": len(credit_bucket["overdue_partner_ids"]),
                    "overdue_customer_names": ", ".join(sorted(credit_bucket["overdue_names"])),
                    "currency_id": self.currency_id.id,
                }
            )

        if summary_vals:
            self.env["wesprime.daily.branch.summary.line"].create(summary_vals)
        if sales_vals:
            self.env["wesprime.daily.branch.sales.line"].create(sales_vals)
        if payment_vals:
            self.env["wesprime.daily.branch.payment.line"].create(payment_vals)
        if cash_vals:
            self.env["wesprime.daily.branch.cash.line"].create(cash_vals)
        if bank_vals:
            self.env["wesprime.daily.branch.bank.line"].create(bank_vals)
        if credit_vals:
            self.env["wesprime.daily.branch.credit.line"].create(credit_vals)
        if inventory_vals:
            self.env["wesprime.daily.branch.inventory.line"].create(inventory_vals)

    def _refresh_dashboard_lines(self):
        for dashboard in self:
            dashboard._clear_lines()
            data = dashboard._build_dashboard_data()
            dashboard._create_dashboard_lines(data)

    def action_refresh(self):
        self.ensure_one()
        self._refresh_dashboard_lines()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_open_cash_controls(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]
        if self.branch_ids:
            domain.append(("branch_ref_id", "in", self.branch_ids.ids))
        return {
            "type": "ir.actions.act_window",
            "name": _("Cash Control Entries"),
            "res_model": "wesprime.branch.cash.control",
            "view_mode": "tree,form",
            "views": [
                (self.env.ref("wesprime_account_reports.view_war_cash_ctrl_tree").id, "tree"),
                (self.env.ref("wesprime_account_reports.view_war_cash_ctrl_form").id, "form"),
            ],
            "domain": domain,
            "context": {"default_company_id": self.company_id.id},
        }

    def action_export_xlsx(self):
        self.ensure_one()
        self._refresh_dashboard_lines()
        attachment = self.env["report.war.branch_dash_xlsx"]._create_xlsx_attachment(self)
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._refresh_dashboard_lines()
        return self.env.ref("wesprime_account_reports.action_war_branch_dash_pdf").report_action(self)

class WesprimeDailyBranchBaseLine(models.AbstractModel):
    _name = "wesprime.daily.branch.base.line"
    _description = "Daily Branch Dashboard Base Line"

    dashboard_id = fields.Many2one("wesprime.daily.branch.dashboard", required=True, ondelete="cascade")
    branch_ref_id = fields.Many2one("wesprime.branch.ref", string="Branch", readonly=True)
    date = fields.Date(readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)


class WesprimeDailyBranchSummaryLine(models.TransientModel):
    _name = "wesprime.daily.branch.summary.line"
    _inherit = "wesprime.daily.branch.base.line"
    _description = "Daily Branch Dashboard Summary Line"
    _order = "branch_ref_id, date, id"

    sales_quantity = fields.Float(readonly=True)
    sales_value = fields.Monetary(currency_field="currency_id", readonly=True)
    cash_sales = fields.Monetary(currency_field="currency_id", readonly=True)
    bank_sales = fields.Monetary(currency_field="currency_id", readonly=True)
    credit_sales = fields.Monetary(currency_field="currency_id", readonly=True)
    cash_difference = fields.Monetary(currency_field="currency_id", readonly=True)
    new_credit = fields.Monetary(currency_field="currency_id", readonly=True)
    total_outstanding = fields.Monetary(currency_field="currency_id", readonly=True)
    overdue_customer_count = fields.Integer(readonly=True)


class WesprimeDailyBranchSalesLine(models.TransientModel):
    _name = "wesprime.daily.branch.sales.line"
    _inherit = "wesprime.daily.branch.base.line"
    _description = "Daily Branch Sales Summary Line"
    _order = "branch_ref_id, date, product_group, id"

    product_group = fields.Selection(PRODUCT_GROUPS, readonly=True)
    quantity = fields.Float(readonly=True)
    value = fields.Monetary(currency_field="currency_id", readonly=True)


class WesprimeDailyBranchPaymentLine(models.TransientModel):
    _name = "wesprime.daily.branch.payment.line"
    _inherit = "wesprime.daily.branch.base.line"
    _description = "Daily Branch Payment Split Line"
    _order = "branch_ref_id, date, id"

    cash_sales = fields.Monetary(currency_field="currency_id", readonly=True)
    bank_sales = fields.Monetary(currency_field="currency_id", string="Bank/UPI Sales", readonly=True)
    credit_sales = fields.Monetary(currency_field="currency_id", readonly=True)


class WesprimeDailyBranchCashLine(models.TransientModel):
    _name = "wesprime.daily.branch.cash.line"
    _inherit = "wesprime.daily.branch.base.line"
    _description = "Daily Branch Cash Control Line"
    _order = "branch_ref_id, date, id"

    cash_control_id = fields.Many2one("wesprime.branch.cash.control", readonly=True)
    opening_cash = fields.Monetary(currency_field="currency_id", readonly=True)
    cash_sales_system = fields.Monetary(currency_field="currency_id", readonly=True)
    expenses_system = fields.Monetary(currency_field="currency_id", readonly=True)
    closing_cash_expected = fields.Monetary(currency_field="currency_id", readonly=True)
    actual_closing_cash = fields.Monetary(currency_field="currency_id", readonly=True)
    difference = fields.Monetary(currency_field="currency_id", readonly=True)


class WesprimeDailyBranchBankLine(models.TransientModel):
    _name = "wesprime.daily.branch.bank.line"
    _inherit = "wesprime.daily.branch.base.line"
    _description = "Daily Branch Bank Control Line"
    _order = "branch_ref_id, date, id"

    cash_control_id = fields.Many2one("wesprime.branch.cash.control", readonly=True)
    bank_sales_system = fields.Monetary(currency_field="currency_id", string="System Bank/UPI Total", readonly=True)
    bank_statement_total = fields.Monetary(currency_field="currency_id", readonly=True)
    bank_difference = fields.Monetary(currency_field="currency_id", readonly=True)


class WesprimeDailyBranchCreditLine(models.TransientModel):
    _name = "wesprime.daily.branch.credit.line"
    _inherit = "wesprime.daily.branch.base.line"
    _description = "Daily Branch Credit Control Line"
    _order = "branch_ref_id, date, id"

    new_credit = fields.Monetary(currency_field="currency_id", readonly=True)
    total_outstanding = fields.Monetary(currency_field="currency_id", readonly=True)
    overdue_amount = fields.Monetary(currency_field="currency_id", readonly=True)
    overdue_customer_count = fields.Integer(readonly=True)
    overdue_customer_names = fields.Char(readonly=True)


class WesprimeDailyBranchInventoryLine(models.TransientModel):
    _name = "wesprime.daily.branch.inventory.line"
    _inherit = "wesprime.daily.branch.base.line"
    _description = "Daily Branch Inventory Snapshot Line"
    _order = "branch_ref_id, date, product_group, id"

    product_group = fields.Selection(PRODUCT_GROUPS, readonly=True)
    opening_stock = fields.Float(readonly=True)
    received = fields.Float(readonly=True)
    sold = fields.Float(readonly=True)
    closing_stock = fields.Float(readonly=True)
    note = fields.Char(readonly=True)
