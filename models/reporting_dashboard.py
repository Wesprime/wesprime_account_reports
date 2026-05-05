from datetime import date

from odoo import _, api, fields, models


class WesprimeReportingDashboard(models.TransientModel):
    _name = "wesprime.reporting.dashboard"
    _description = "Wesprime Reporting Dashboard"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    as_of_date = fields.Date(required=True, default=fields.Date.context_today)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True)
    total_receivables = fields.Monetary(
        compute="_compute_summary",
        currency_field="currency_id",
        string="Total Receivables",
    )
    total_payables = fields.Monetary(
        compute="_compute_summary",
        currency_field="currency_id",
        string="Total Payables",
    )
    bank_balance_total = fields.Monetary(
        compute="_compute_summary",
        currency_field="currency_id",
        string="Bank Balance",
    )
    cash_balance_total = fields.Monetary(
        compute="_compute_summary",
        currency_field="currency_id",
        string="Cash Balance",
    )
    customer_invoice_total = fields.Monetary(
        compute="_compute_summary",
        currency_field="currency_id",
        string="Customer Invoice Totals",
    )
    vendor_bill_total = fields.Monetary(
        compute="_compute_summary",
        currency_field="currency_id",
        string="Vendor Bill Totals",
    )
    bank_balance_line_ids = fields.One2many(
        "wesprime.dashboard.journal.balance",
        "dashboard_id",
        domain=[("journal_type", "=", "bank")],
        string="Bank Balance Summary",
    )
    cash_balance_line_ids = fields.One2many(
        "wesprime.dashboard.journal.balance",
        "dashboard_id",
        domain=[("journal_type", "=", "cash")],
        string="Cash Balance Summary",
    )
    top_customer_line_ids = fields.One2many(
        "wesprime.dashboard.partner.total",
        "dashboard_id",
        domain=[("partner_role", "=", "customer")],
        string="Top Customers",
    )
    top_vendor_line_ids = fields.One2many(
        "wesprime.dashboard.partner.total",
        "dashboard_id",
        domain=[("partner_role", "=", "vendor")],
        string="Top Vendors",
    )
    recent_move_line_ids = fields.One2many(
        "wesprime.dashboard.recent.move",
        "dashboard_id",
        string="Recent Journal Entries",
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
                "as_of_date": fields.Date.context_today(self),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Reporting Dashboard"),
            "res_model": self._name,
            "view_mode": "form",
            "view_id": self.env.ref("wesprime_account_reports.view_wesprime_reporting_dashboard_form").id,
            "res_id": dashboard.id,
            "target": "current",
        }

    def _move_line_sum(self, domain, field_name):
        result = self.env["account.move.line"].read_group(domain, [field_name], [])
        return result and result[0].get(field_name, 0.0) or 0.0

    def _move_sum(self, domain, field_name):
        result = self.env["account.move"].read_group(domain, [field_name], [])
        return result and result[0].get(field_name, 0.0) or 0.0

    def _journal_balance_map(self, journal_type):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("journal_id.type", "=", journal_type),
            ("parent_state", "=", "posted"),
        ]
        if self.as_of_date:
            domain.append(("date", "<=", self.as_of_date))
        groups = self.env["account.move.line"].read_group(domain, ["balance"], ["journal_id"], lazy=False)
        return {
            group["journal_id"][0]: group.get("balance", 0.0)
            for group in groups
            if group.get("journal_id")
        }

    @api.depends("company_id", "as_of_date")
    def _compute_summary(self):
        for dashboard in self:
            line_domain = [
                ("company_id", "=", dashboard.company_id.id),
                ("parent_state", "=", "posted"),
            ]
            if dashboard.as_of_date:
                line_domain.append(("date", "<=", dashboard.as_of_date))

            receivable = dashboard._move_line_sum(
                line_domain + [("account_id.account_type", "=", "asset_receivable")],
                "amount_residual",
            )
            payable = dashboard._move_line_sum(
                line_domain + [("account_id.account_type", "=", "liability_payable")],
                "amount_residual",
            )
            dashboard.total_receivables = receivable
            dashboard.total_payables = abs(payable)
            dashboard.bank_balance_total = sum(dashboard._journal_balance_map("bank").values())
            dashboard.cash_balance_total = sum(dashboard._journal_balance_map("cash").values())

            move_domain = [
                ("company_id", "=", dashboard.company_id.id),
                ("state", "=", "posted"),
            ]
            if dashboard.as_of_date:
                move_domain.append(("invoice_date", "<=", dashboard.as_of_date))

            dashboard.customer_invoice_total = dashboard._move_sum(
                move_domain + [("move_type", "in", ("out_invoice", "out_refund"))],
                "amount_total_signed",
            )
            dashboard.vendor_bill_total = abs(
                dashboard._move_sum(
                    move_domain + [("move_type", "in", ("in_invoice", "in_refund"))],
                    "amount_total_signed",
                )
            )

    def _period_start(self):
        self.ensure_one()
        reference_date = self.as_of_date or fields.Date.context_today(self)
        return date(reference_date.year, 1, 1)

    def _refresh_dashboard_lines(self):
        for dashboard in self:
            dashboard.bank_balance_line_ids.unlink()
            dashboard.cash_balance_line_ids.unlink()
            dashboard.top_customer_line_ids.unlink()
            dashboard.top_vendor_line_ids.unlink()
            dashboard.recent_move_line_ids.unlink()
            dashboard._create_journal_balance_lines("bank")
            dashboard._create_journal_balance_lines("cash")
            dashboard._create_top_partner_lines("customer")
            dashboard._create_top_partner_lines("vendor")
            dashboard._create_recent_move_lines()

    def _create_journal_balance_lines(self, journal_type):
        self.ensure_one()
        balance_by_journal = self._journal_balance_map(journal_type)
        journals = self.env["account.journal"].search(
            [("company_id", "=", self.company_id.id), ("type", "=", journal_type)],
            order="sequence, name",
        )
        values = [
            {
                "dashboard_id": self.id,
                "journal_id": journal.id,
                "journal_type": journal_type,
                "balance": balance_by_journal.get(journal.id, 0.0),
                "currency_id": self.currency_id.id,
            }
            for journal in journals
        ]
        if values:
            self.env["wesprime.dashboard.journal.balance"].create(values)

    def _create_top_partner_lines(self, role):
        self.ensure_one()
        if role == "customer":
            move_types = ("out_invoice", "out_refund")
        else:
            move_types = ("in_invoice", "in_refund")

        domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "=", "posted"),
            ("move_type", "in", move_types),
            ("partner_id", "!=", False),
        ]
        if self.as_of_date:
            domain.append(("invoice_date", "<=", self.as_of_date))
        domain.append(("invoice_date", ">=", self._period_start()))

        groups = self.env["account.move"].read_group(
            domain,
            ["partner_id", "amount_total_signed"],
            ["partner_id"],
            lazy=False,
        )
        sorted_groups = sorted(
            groups,
            key=lambda group: abs(group.get("amount_total_signed", 0.0)),
            reverse=True,
        )[:5]
        values = []
        for sequence, group in enumerate(sorted_groups, start=1):
            partner = group.get("partner_id")
            if not partner:
                continue
            amount = group.get("amount_total_signed", 0.0)
            values.append(
                {
                    "dashboard_id": self.id,
                    "sequence": sequence,
                    "partner_id": partner[0],
                    "partner_role": role,
                    "amount_total": abs(amount) if role == "vendor" else amount,
                    "currency_id": self.currency_id.id,
                }
            )
        if values:
            self.env["wesprime.dashboard.partner.total"].create(values)

    def _create_recent_move_lines(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "=", "posted"),
        ]
        if self.as_of_date:
            domain.append(("date", "<=", self.as_of_date))
        moves = self.env["account.move"].search(
            domain,
            order="date desc, id desc",
            limit=10,
        )
        values = [
            {
                "dashboard_id": self.id,
                "sequence": sequence,
                "move_id": move.id,
                "date": move.date,
                "journal_id": move.journal_id.id,
                "partner_id": move.partner_id.id,
                "ref": move.ref or "",
                "amount_total": abs(move.amount_total_signed),
                "currency_id": self.currency_id.id,
            }
            for sequence, move in enumerate(moves, start=1)
        ]
        if values:
            self.env["wesprime.dashboard.recent.move"].create(values)

    def action_refresh(self):
        self.ensure_one()
        self._refresh_dashboard_lines()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_open_partner_ledger(self):
        self.ensure_one()
        action = self.env.ref("base_accounting_kit.action_partner_leadger").read()[0]
        action["context"] = {
            "default_company_id": self.company_id.id,
            "default_date_to": self.as_of_date,
        }
        return action

    def action_open_bank_book(self):
        self.ensure_one()
        journals = self.env["account.journal"].search(
            [("company_id", "=", self.company_id.id), ("type", "=", "bank")]
        )
        return self.env["wesprime.daily.transaction.summary.wizard"]._action_open_wizard(
            _("Bank Book"),
            {
                "default_company_id": self.company_id.id,
                "default_start_date": self._period_start(),
                "default_end_date": self.as_of_date,
                "default_journal_ids": [(6, 0, journals.ids)],
            },
        )

    def action_open_cash_book(self):
        self.ensure_one()
        journals = self.env["account.journal"].search(
            [("company_id", "=", self.company_id.id), ("type", "=", "cash")]
        )
        return self.env["wesprime.daily.transaction.summary.wizard"]._action_open_wizard(
            _("Cash Book"),
            {
                "default_company_id": self.company_id.id,
                "default_start_date": self._period_start(),
                "default_end_date": self.as_of_date,
                "default_journal_ids": [(6, 0, journals.ids)],
            },
        )

    def action_open_day_book(self):
        self.ensure_one()
        return self.env["wesprime.daily.transaction.summary.wizard"]._action_open_wizard(
            _("Day Book"),
            {
                "default_company_id": self.company_id.id,
                "default_start_date": self.as_of_date,
                "default_end_date": self.as_of_date,
            },
        )

    def action_open_aged_partner_balance(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Aged Partner Balance"),
            "res_model": "wesprime.aged.partner.balance.wizard",
            "view_mode": "form",
            "view_id": self.env.ref("wesprime_account_reports.view_wesprime_aged_partner_balance_wizard_form").id,
            "target": "new",
            "context": {
                "default_company_id": self.company_id.id,
                "default_as_of_date": self.as_of_date,
            },
        }


class WesprimeDashboardJournalBalance(models.TransientModel):
    _name = "wesprime.dashboard.journal.balance"
    _description = "Wesprime Dashboard Journal Balance"
    _order = "journal_type, journal_id"

    dashboard_id = fields.Many2one("wesprime.reporting.dashboard", required=True, ondelete="cascade")
    journal_id = fields.Many2one("account.journal", readonly=True)
    journal_type = fields.Selection([("bank", "Bank"), ("cash", "Cash")], readonly=True)
    balance = fields.Monetary(currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)


class WesprimeDashboardPartnerTotal(models.TransientModel):
    _name = "wesprime.dashboard.partner.total"
    _description = "Wesprime Dashboard Partner Total"
    _order = "sequence, id"

    dashboard_id = fields.Many2one("wesprime.reporting.dashboard", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    partner_id = fields.Many2one("res.partner", readonly=True)
    partner_role = fields.Selection([("customer", "Customer"), ("vendor", "Vendor")], readonly=True)
    amount_total = fields.Monetary(currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)


class WesprimeDashboardRecentMove(models.TransientModel):
    _name = "wesprime.dashboard.recent.move"
    _description = "Wesprime Dashboard Recent Move"
    _order = "sequence, id"

    dashboard_id = fields.Many2one("wesprime.reporting.dashboard", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True)
    date = fields.Date(readonly=True)
    journal_id = fields.Many2one("account.journal", readonly=True)
    partner_id = fields.Many2one("res.partner", readonly=True)
    ref = fields.Char(string="Reference", readonly=True)
    amount_total = fields.Monetary(currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
