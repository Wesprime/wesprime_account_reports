import base64
import io

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - handled at runtime in Odoo
    xlsxwriter = None

from odoo import _, fields, models
from odoo.exceptions import UserError


class WesprimePartnerLedgerWizard(models.TransientModel):
    _name = "wesprime.partner.ledger.wizard"
    _description = "Wesprime Partner Ledger Wizard"

    date_from = fields.Date(string="Start Date")
    date_to = fields.Date(string="End Date", default=fields.Date.context_today)
    journal_ids = fields.Many2many(
        "account.journal",
        "wesprime_partner_ledger_journal_rel",
        "wizard_id",
        "journal_id",
        string="Journals",
        domain="[('company_id', '=', company_id)]",
    )
    partner_ids = fields.Many2many(
        "res.partner",
        "wesprime_partner_ledger_partner_rel",
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
        "wesprime.partner.ledger.line",
        "wizard_id",
        string="Ledger Lines",
    )

    def _base_line_domain(self, include_date_from=True, opening=False):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("account_id.account_type", "in", ("asset_receivable", "liability_payable")),
            ("partner_id", "!=", False),
        ]
        if self.target_move == "posted":
            domain.append(("parent_state", "=", "posted"))
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        if self.date_to:
            domain.append(("date", "<=", self.date_to))
        if opening and self.date_from:
            domain.append(("date", "<", self.date_from))
        elif include_date_from and self.date_from:
            domain.append(("date", ">=", self.date_from))
        return domain

    def _get_report_partners(self):
        self.ensure_one()
        if self.partner_ids:
            return self.partner_ids.sorted(key=lambda partner: partner.display_name or "")

        domain = self._base_line_domain(include_date_from=False)
        groups = self.env["account.move.line"].read_group(
            domain,
            ["partner_id"],
            ["partner_id"],
            lazy=False,
        )
        partner_ids = [group["partner_id"][0] for group in groups if group.get("partner_id")]
        return self.env["res.partner"].browse(partner_ids).sorted(key=lambda partner: partner.display_name or "")

    def _line_values_from_move_line(self, move_line, sequence, running_balance):
        return {
            "wizard_id": self.id,
            "sequence": sequence,
            "date": move_line.date,
            "move_id": move_line.move_id.id,
            "move_name": move_line.move_id.name or "/",
            "journal_id": move_line.journal_id.id,
            "partner_id": move_line.partner_id.id,
            "account_id": move_line.account_id.id,
            "label": move_line.name or move_line.ref or move_line.move_id.ref or "",
            "ref": move_line.ref or move_line.move_id.ref or "",
            "debit": move_line.debit,
            "credit": move_line.credit,
            "line_balance": move_line.balance,
            "balance": running_balance,
            "amount_currency": move_line.amount_currency,
            "currency_id": (move_line.currency_id or self.company_id.currency_id).id,
            "company_id": self.company_id.id,
        }

    def _generate_lines(self):
        self.ensure_one()
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise UserError(_("Start Date cannot be after End Date."))

        self.result_line_ids.unlink()

        AccountMoveLine = self.env["account.move.line"]
        values = []
        sequence = 0

        for partner in self._get_report_partners():
            running_balance = 0.0
            if self.date_from:
                opening_lines = AccountMoveLine.search(
                    self._base_line_domain(opening=True) + [("partner_id", "=", partner.id)]
                )
                opening_debit = sum(opening_lines.mapped("debit"))
                opening_credit = sum(opening_lines.mapped("credit"))
                running_balance = opening_debit - opening_credit
                if opening_debit or opening_credit:
                    sequence += 1
                    values.append(
                        {
                            "wizard_id": self.id,
                            "sequence": sequence,
                            "partner_id": partner.id,
                            "label": _("Opening Balance"),
                            "debit": opening_debit,
                            "credit": opening_credit,
                            "line_balance": running_balance,
                            "balance": running_balance,
                            "currency_id": self.company_id.currency_id.id,
                            "company_id": self.company_id.id,
                            "is_initial": True,
                        }
                    )

            move_lines = AccountMoveLine.search(
                self._base_line_domain() + [("partner_id", "=", partner.id)],
                order="partner_id, date, move_name, id",
            )
            for move_line in move_lines:
                sequence += 1
                running_balance += move_line.balance
                values.append(self._line_values_from_move_line(move_line, sequence, running_balance))

        if values:
            self.env["wesprime.partner.ledger.line"].create(values)
        return self.result_line_ids

    def action_view(self):
        self.ensure_one()
        self._generate_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("Partner Ledger"),
            "res_model": "wesprime.partner.ledger.line",
            "view_mode": "tree,form",
            "views": [
                (self.env.ref("wesprime_account_reports.view_wesprime_partner_ledger_line_tree").id, "tree"),
                (self.env.ref("wesprime_account_reports.view_wesprime_partner_ledger_line_form").id, "form"),
            ],
            "domain": [("wizard_id", "=", self.id)],
            "context": {"create": False, "edit": False},
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._generate_lines()
        return self.env.ref("wesprime_account_reports.action_report_partner_ledger_pdf").report_action(self)

    def action_print_xlsx(self):
        self.ensure_one()
        if xlsxwriter is None:
            raise UserError(_("The xlsxwriter Python package is required to export Excel files."))
        self._generate_lines()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(_("Partner Ledger")[:31])

        title_format = workbook.add_format({"bold": True, "font_size": 14})
        header_format = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
        money_format = workbook.add_format({"num_format": "#,##0.00", "border": 1})
        text_format = workbook.add_format({"border": 1})
        initial_format = workbook.add_format({"bold": True, "bg_color": "#F4F4F4", "border": 1})

        sheet.merge_range(0, 0, 0, 9, _("Partner Ledger"), title_format)
        sheet.write(1, 0, _("Company"), header_format)
        sheet.write(1, 1, self.company_id.display_name or "", text_format)
        sheet.write(2, 0, _("Period"), header_format)
        sheet.write(2, 1, "%s - %s" % (self.date_from or "", self.date_to or ""), text_format)

        headers = [
            _("Date"),
            _("Partner"),
            _("Journal"),
            _("Entry"),
            _("Account"),
            _("Label"),
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
            row_format = initial_format if line.is_initial else text_format
            sheet.write(row, 0, line.date and line.date.strftime("%Y-%m-%d") or "", row_format)
            sheet.write(row, 1, line.partner_id.display_name or "", row_format)
            sheet.write(row, 2, line.journal_id.display_name or "", row_format)
            sheet.write(row, 3, line.move_name or "", row_format)
            sheet.write(row, 4, line.account_id.display_name or "", row_format)
            sheet.write(row, 5, line.label or "", row_format)
            sheet.write_number(row, 6, line.debit or 0.0, money_format)
            sheet.write_number(row, 7, line.credit or 0.0, money_format)
            sheet.write_number(row, 8, line.balance or 0.0, money_format)
            sheet.write_number(row, 9, line.amount_currency or 0.0, money_format)

        row += 2
        sheet.write(row, 5, _("Total"), header_format)
        sheet.write_number(row, 6, sum(self.result_line_ids.mapped("debit")), money_format)
        sheet.write_number(row, 7, sum(self.result_line_ids.mapped("credit")), money_format)
        sheet.write_number(row, 8, sum(self.result_line_ids.mapped("line_balance")), money_format)

        sheet.freeze_panes(5, 0)
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 5, 22)
        sheet.set_column(6, 9, 14)
        workbook.close()

        attachment = self.env["ir.attachment"].create(
            {
                "name": "partner_ledger.xlsx",
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


class WesprimePartnerLedgerLine(models.TransientModel):
    _name = "wesprime.partner.ledger.line"
    _description = "Wesprime Partner Ledger Line"
    _order = "sequence, id"

    wizard_id = fields.Many2one("wesprime.partner.ledger.wizard", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    date = fields.Date()
    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True)
    move_name = fields.Char(string="Entry", readonly=True)
    journal_id = fields.Many2one("account.journal", readonly=True)
    partner_id = fields.Many2one("res.partner", readonly=True)
    account_id = fields.Many2one("account.account", readonly=True)
    label = fields.Char(readonly=True)
    ref = fields.Char(string="Reference", readonly=True)
    debit = fields.Monetary(currency_field="company_currency_id", readonly=True)
    credit = fields.Monetary(currency_field="company_currency_id", readonly=True)
    line_balance = fields.Monetary(string="Line Balance", currency_field="company_currency_id", readonly=True)
    balance = fields.Monetary(currency_field="company_currency_id", readonly=True)
    amount_currency = fields.Monetary(currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    company_currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        readonly=True,
    )
    is_initial = fields.Boolean(readonly=True)
