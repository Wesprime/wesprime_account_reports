import base64
import io

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - handled at runtime in Odoo
    xlsxwriter = None

from odoo import _, fields, models
from odoo.exceptions import UserError


class WesprimeDailyTransactionSummaryWizard(models.TransientModel):
    _name = "wesprime.daily.transaction.summary.wizard"
    _description = "Daily Transaction Summary Wizard"

    start_date = fields.Date(string="Start Date", required=True, default=fields.Date.context_today)
    end_date = fields.Date(string="End Date", required=True, default=fields.Date.context_today)
    journal_ids = fields.Many2many(
        "account.journal",
        "wesprime_daily_summary_journal_rel",
        "wizard_id",
        "journal_id",
        string="Journals",
        domain="[('company_id', '=', company_id)]",
    )
    partner_ids = fields.Many2many(
        "res.partner",
        "wesprime_daily_summary_partner_rel",
        "wizard_id",
        "partner_id",
        string="Partners",
    )
    target_move = fields.Selection(
        [("posted", "Posted Entries"), ("all", "All Entries")],
        string="Target Moves",
        default="posted",
        required=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    result_line_ids = fields.One2many(
        "wesprime.daily.transaction.summary.line",
        "wizard_id",
        string="Transaction Lines",
    )

    def _get_line_domain(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("date", ">=", self.start_date),
            ("date", "<=", self.end_date),
            ("display_type", "not in", ("line_section", "line_note")),
        ]
        if self.target_move == "posted":
            domain.append(("parent_state", "=", "posted"))
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        if self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))
        return domain

    def _generate_lines(self):
        self.ensure_one()
        if self.start_date > self.end_date:
            raise UserError(_("Start Date cannot be after End Date."))

        self.result_line_ids.unlink()
        move_lines = self.env["account.move.line"].search(
            self._get_line_domain(),
            order="date, journal_id, move_name, id",
        )
        values = []
        for sequence, line in enumerate(move_lines, start=1):
            values.append(
                {
                    "wizard_id": self.id,
                    "sequence": sequence,
                    "date": line.date,
                    "move_id": line.move_id.id,
                    "move_name": line.move_id.name or "/",
                    "journal_id": line.journal_id.id,
                    "partner_id": line.partner_id.id,
                    "account_id": line.account_id.id,
                    "label": line.name or line.ref or line.move_id.ref or "",
                    "ref": line.ref or line.move_id.ref or "",
                    "debit": line.debit,
                    "credit": line.credit,
                    "balance": line.balance,
                    "amount_currency": line.amount_currency,
                    "currency_id": (line.currency_id or self.company_id.currency_id).id,
                    "company_id": self.company_id.id,
                }
            )
        if values:
            self.env["wesprime.daily.transaction.summary.line"].create(values)
        return self.result_line_ids

    def _action_open_wizard(self, name=None, extra_context=None):
        context = dict(self.env.context)
        if extra_context:
            context.update(extra_context)
        return {
            "type": "ir.actions.act_window",
            "name": name or _("Daily Transaction Summary"),
            "res_model": self._name,
            "view_mode": "form",
            "view_id": self.env.ref("wesprime_account_reports.view_daily_transaction_summary_wizard_form").id,
            "target": "new",
            "context": context,
        }

    def action_view(self):
        self.ensure_one()
        self._generate_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("Daily Transaction Summary"),
            "res_model": "wesprime.daily.transaction.summary.line",
            "view_mode": "tree,form",
            "views": [
                (self.env.ref("wesprime_account_reports.view_daily_transaction_summary_line_tree").id, "tree"),
                (self.env.ref("wesprime_account_reports.view_daily_transaction_summary_line_form").id, "form"),
            ],
            "domain": [("wizard_id", "=", self.id)],
            "context": {"create": False, "edit": False},
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._generate_lines()
        return self.env.ref("wesprime_account_reports.action_report_daily_transaction_summary_pdf").report_action(self)

    def action_print_xlsx(self):
        self.ensure_one()
        if xlsxwriter is None:
            raise UserError(_("The xlsxwriter Python package is required to export Excel files."))
        self._generate_lines()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(_("Daily Summary")[:31])

        title_format = workbook.add_format({"bold": True, "font_size": 14})
        header_format = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
        money_format = workbook.add_format({"num_format": "#,##0.00", "border": 1})
        text_format = workbook.add_format({"border": 1})

        sheet.merge_range(0, 0, 0, 10, _("Daily Transaction Summary"), title_format)
        sheet.write(1, 0, _("Company"), header_format)
        sheet.write(1, 1, self.company_id.display_name or "", text_format)
        sheet.write(2, 0, _("Period"), header_format)
        sheet.write(2, 1, "%s - %s" % (self.start_date or "", self.end_date or ""), text_format)

        headers = [
            _("Date"),
            _("Journal"),
            _("Entry"),
            _("Partner"),
            _("Account"),
            _("Label"),
            _("Reference"),
            _("Debit"),
            _("Credit"),
            _("Balance"),
            _("Currency Amount"),
        ]
        row = 4
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)

        for line in self.result_line_ids:
            row += 1
            sheet.write(row, 0, line.date and line.date.strftime("%Y-%m-%d") or "", text_format)
            sheet.write(row, 1, line.journal_id.display_name or "", text_format)
            sheet.write(row, 2, line.move_name or "", text_format)
            sheet.write(row, 3, line.partner_id.display_name or "", text_format)
            sheet.write(row, 4, line.account_id.display_name or "", text_format)
            sheet.write(row, 5, line.label or "", text_format)
            sheet.write(row, 6, line.ref or "", text_format)
            sheet.write_number(row, 7, line.debit or 0.0, money_format)
            sheet.write_number(row, 8, line.credit or 0.0, money_format)
            sheet.write_number(row, 9, line.balance or 0.0, money_format)
            sheet.write_number(row, 10, line.amount_currency or 0.0, money_format)

        row += 2
        sheet.write(row, 6, _("Total"), header_format)
        sheet.write_number(row, 7, sum(self.result_line_ids.mapped("debit")), money_format)
        sheet.write_number(row, 8, sum(self.result_line_ids.mapped("credit")), money_format)
        sheet.write_number(row, 9, sum(self.result_line_ids.mapped("balance")), money_format)

        sheet.freeze_panes(5, 0)
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 6, 22)
        sheet.set_column(7, 10, 14)
        workbook.close()

        attachment = self.env["ir.attachment"].create(
            {
                "name": "daily_transaction_summary.xlsx",
                "type": "binary",
                "datas": base64.b64encode(output.getvalue()),
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }


class WesprimeDailyTransactionSummaryLine(models.TransientModel):
    _name = "wesprime.daily.transaction.summary.line"
    _description = "Daily Transaction Summary Line"
    _order = "sequence, id"

    wizard_id = fields.Many2one("wesprime.daily.transaction.summary.wizard", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    date = fields.Date(readonly=True)
    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True)
    move_name = fields.Char(string="Entry", readonly=True)
    journal_id = fields.Many2one("account.journal", readonly=True)
    partner_id = fields.Many2one("res.partner", readonly=True)
    account_id = fields.Many2one("account.account", readonly=True)
    label = fields.Char(readonly=True)
    ref = fields.Char(string="Reference", readonly=True)
    debit = fields.Monetary(currency_field="company_currency_id", readonly=True)
    credit = fields.Monetary(currency_field="company_currency_id", readonly=True)
    balance = fields.Monetary(currency_field="company_currency_id", readonly=True)
    amount_currency = fields.Monetary(currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    company_currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        readonly=True,
    )
