import base64
import io

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - handled at runtime in Odoo
    xlsxwriter = None

from odoo import _, fields, models
from odoo.exceptions import UserError


class WesprimeAgedPartnerBalanceWizard(models.TransientModel):
    _name = "wesprime.aged.partner.balance.wizard"
    _description = "Wesprime Aged Partner Balance Wizard"

    as_of_date = fields.Date(string="As of Date", required=True, default=fields.Date.context_today)
    partner_ids = fields.Many2many(
        "res.partner",
        "wesprime_aged_partner_balance_partner_rel",
        "wizard_id",
        "partner_id",
        string="Partners",
    )
    account_type = fields.Selection(
        [
            ("both", "Receivable and Payable"),
            ("receivable", "Receivable"),
            ("payable", "Payable"),
        ],
        default="both",
        required=True,
    )
    target_move = fields.Selection(
        [("posted", "Posted Entries"), ("all", "All Entries")],
        default="posted",
        required=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    result_line_ids = fields.One2many(
        "wesprime.aged.partner.balance.line",
        "wizard_id",
        string="Aged Balance Lines",
    )

    def _account_types(self):
        self.ensure_one()
        if self.account_type == "receivable":
            return ("asset_receivable",)
        if self.account_type == "payable":
            return ("liability_payable",)
        return ("asset_receivable", "liability_payable")

    def _line_domain(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("partner_id", "!=", False),
            ("account_id.account_type", "in", self._account_types()),
            ("amount_residual", "!=", 0.0),
            ("date", "<=", self.as_of_date),
        ]
        if self.target_move == "posted":
            domain.append(("parent_state", "=", "posted"))
        if self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))
        return domain

    def _bucket_name(self, line):
        self.ensure_one()
        due_date = line.date_maturity or line.date
        days = (self.as_of_date - due_date).days
        if days <= 0:
            return "not_due"
        if days <= 30:
            return "age_1_30"
        if days <= 60:
            return "age_31_60"
        if days <= 90:
            return "age_61_90"
        if days <= 120:
            return "age_91_120"
        return "older"

    def _generate_lines(self):
        self.ensure_one()
        self.result_line_ids.unlink()
        buckets_by_partner = {}
        move_lines = self.env["account.move.line"].search(self._line_domain(), order="partner_id, date_maturity, date, id")

        for line in move_lines:
            partner_values = buckets_by_partner.setdefault(
                line.partner_id.id,
                {
                    "not_due": 0.0,
                    "age_1_30": 0.0,
                    "age_31_60": 0.0,
                    "age_61_90": 0.0,
                    "age_91_120": 0.0,
                    "older": 0.0,
                },
            )
            amount = line.amount_residual
            if self.account_type == "payable":
                amount = abs(amount)
            partner_values[self._bucket_name(line)] += amount

        values = []
        for sequence, (partner_id, bucket_values) in enumerate(buckets_by_partner.items(), start=1):
            total = sum(bucket_values.values())
            values.append(
                {
                    "wizard_id": self.id,
                    "sequence": sequence,
                    "partner_id": partner_id,
                    "not_due": bucket_values["not_due"],
                    "age_1_30": bucket_values["age_1_30"],
                    "age_31_60": bucket_values["age_31_60"],
                    "age_61_90": bucket_values["age_61_90"],
                    "age_91_120": bucket_values["age_91_120"],
                    "older": bucket_values["older"],
                    "total": total,
                    "company_id": self.company_id.id,
                    "currency_id": self.company_id.currency_id.id,
                }
            )
        if values:
            self.env["wesprime.aged.partner.balance.line"].create(values)
        return self.result_line_ids

    def action_view(self):
        self.ensure_one()
        self._generate_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("Aged Partner Balance"),
            "res_model": "wesprime.aged.partner.balance.line",
            "view_mode": "tree,form",
            "views": [
                (self.env.ref("wesprime_account_reports.view_wesprime_aged_partner_balance_line_tree").id, "tree"),
                (self.env.ref("wesprime_account_reports.view_wesprime_aged_partner_balance_line_form").id, "form"),
            ],
            "domain": [("wizard_id", "=", self.id)],
            "context": {"create": False, "edit": False},
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._generate_lines()
        return self.env.ref("wesprime_account_reports.action_report_aged_partner_balance_pdf").report_action(self)

    def action_print_xlsx(self):
        self.ensure_one()
        if xlsxwriter is None:
            raise UserError(_("The xlsxwriter Python package is required to export Excel files."))
        self._generate_lines()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(_("Aged Balance")[:31])
        title_format = workbook.add_format({"bold": True, "font_size": 14})
        header_format = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
        money_format = workbook.add_format({"num_format": "#,##0.00", "border": 1})
        text_format = workbook.add_format({"border": 1})

        sheet.merge_range(0, 0, 0, 7, _("Aged Partner Balance"), title_format)
        sheet.write(1, 0, _("Company"), header_format)
        sheet.write(1, 1, self.company_id.display_name or "", text_format)
        sheet.write(2, 0, _("As of Date"), header_format)
        sheet.write(2, 1, self.as_of_date and self.as_of_date.strftime("%Y-%m-%d") or "", text_format)

        headers = [
            _("Partner"),
            _("Not Due"),
            _("1-30"),
            _("31-60"),
            _("61-90"),
            _("91-120"),
            _("Older"),
            _("Total"),
        ]
        row = 4
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)

        for line in self.result_line_ids:
            row += 1
            sheet.write(row, 0, line.partner_id.display_name or "", text_format)
            sheet.write_number(row, 1, line.not_due or 0.0, money_format)
            sheet.write_number(row, 2, line.age_1_30 or 0.0, money_format)
            sheet.write_number(row, 3, line.age_31_60 or 0.0, money_format)
            sheet.write_number(row, 4, line.age_61_90 or 0.0, money_format)
            sheet.write_number(row, 5, line.age_91_120 or 0.0, money_format)
            sheet.write_number(row, 6, line.older or 0.0, money_format)
            sheet.write_number(row, 7, line.total or 0.0, money_format)

        row += 2
        sheet.write(row, 0, _("Total"), header_format)
        for col, field_name in enumerate(("not_due", "age_1_30", "age_31_60", "age_61_90", "age_91_120", "older", "total"), start=1):
            sheet.write_number(row, col, sum(self.result_line_ids.mapped(field_name)), money_format)

        sheet.freeze_panes(5, 0)
        sheet.set_column(0, 0, 28)
        sheet.set_column(1, 7, 14)
        workbook.close()

        attachment = self.env["ir.attachment"].create(
            {
                "name": "aged_partner_balance.xlsx",
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


class WesprimeAgedPartnerBalanceLine(models.TransientModel):
    _name = "wesprime.aged.partner.balance.line"
    _description = "Wesprime Aged Partner Balance Line"
    _order = "sequence, id"

    wizard_id = fields.Many2one("wesprime.aged.partner.balance.wizard", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    partner_id = fields.Many2one("res.partner", readonly=True)
    not_due = fields.Monetary(currency_field="currency_id", readonly=True)
    age_1_30 = fields.Monetary(string="1-30", currency_field="currency_id", readonly=True)
    age_31_60 = fields.Monetary(string="31-60", currency_field="currency_id", readonly=True)
    age_61_90 = fields.Monetary(string="61-90", currency_field="currency_id", readonly=True)
    age_91_120 = fields.Monetary(string="91-120", currency_field="currency_id", readonly=True)
    older = fields.Monetary(currency_field="currency_id", readonly=True)
    total = fields.Monetary(currency_field="currency_id", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
