from odoo import api, fields, models


class WesprimeBranchCashControl(models.Model):
    _name = "wesprime.branch.cash.control"
    _description = "Daily Branch Cash and Bank Control"
    _order = "date desc, branch_ref_id"

    date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    branch_ref_id = fields.Many2one(
        "wesprime.branch.ref",
        string="Branch",
        required=True,
        ondelete="restrict",
        index=True,
    )
    branch_name = fields.Char(related="branch_ref_id.name", string="Branch Name", store=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True)
    opening_cash = fields.Monetary(currency_field="currency_id")
    cash_sales_system = fields.Monetary(
        string="Cash Sales",
        currency_field="currency_id",
        readonly=True,
    )
    expenses_system = fields.Monetary(
        string="Expenses",
        currency_field="currency_id",
        readonly=True,
    )
    closing_cash_expected = fields.Monetary(
        string="Expected Closing Cash",
        currency_field="currency_id",
        compute="_compute_cash_totals",
        store=True,
    )
    actual_closing_cash = fields.Monetary(currency_field="currency_id")
    difference = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_cash_totals",
        store=True,
    )
    bank_sales_system = fields.Monetary(
        string="UPI/Bank Total",
        currency_field="currency_id",
        readonly=True,
    )
    bank_statement_total = fields.Monetary(currency_field="currency_id")
    bank_difference = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_cash_totals",
        store=True,
    )
    notes = fields.Text()

    _sql_constraints = [
        (
            "branch_cash_control_day_uniq",
            "unique(date, branch_ref_id, company_id)",
            "A cash control entry already exists for this branch and date.",
        )
    ]

    @api.depends(
        "opening_cash",
        "cash_sales_system",
        "expenses_system",
        "actual_closing_cash",
        "bank_sales_system",
        "bank_statement_total",
    )
    def _compute_cash_totals(self):
        for control in self:
            control.closing_cash_expected = (
                control.opening_cash + control.cash_sales_system - control.expenses_system
            )
            control.difference = control.actual_closing_cash - control.closing_cash_expected
            control.bank_difference = control.bank_statement_total - control.bank_sales_system
