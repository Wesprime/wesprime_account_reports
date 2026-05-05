import base64
import io

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - handled at runtime in Odoo
    xlsxwriter = None

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import get_lang


class AccountPartnerLedger(models.TransientModel):
    _inherit = "account.report.partner.ledger"

    partner_ids = fields.Many2many("res.partner", string="Partners")

    def _partner_ledger_account_types(self):
        self.ensure_one()
        if self.result_selection == "customer":
            return ["asset_receivable"]
        if self.result_selection == "supplier":
            return ["liability_payable"]
        return ["asset_receivable", "liability_payable"]

    def _partner_ledger_domain(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("partner_id", "!=", False),
            ("account_id.account_type", "in", self._partner_ledger_account_types()),
        ]
        if self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))
        if self.date_from:
            domain.append(("date", ">=", self.date_from))
        if self.date_to:
            domain.append(("date", "<=", self.date_to))
        if self.target_move == "posted":
            domain.append(("parent_state", "=", "posted"))
        if not self.reconciled:
            domain.append(("full_reconcile_id", "=", False))
        return domain

    def _validate_partner_ledger_dates(self):
        self.ensure_one()
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise UserError(_("Start Date cannot be after End Date."))

    def check_report(self):
        self.ensure_one()
        self._validate_partner_ledger_dates()
        data = {
            "ids": self.env.context.get("active_ids", []),
            "model": self.env.context.get("active_model", "ir.ui.menu"),
            "form": self.read(
                [
                    "date_from",
                    "date_to",
                    "journal_ids",
                    "target_move",
                    "company_id",
                    "partner_ids",
                ]
            )[0],
        }
        used_context = self._build_contexts(data)
        data["form"]["used_context"] = dict(used_context, lang=get_lang(self.env).code)
        return self.with_context(discard_logo_check=True)._print_report(data)

    def pre_print_report(self, data):
        data = super().pre_print_report(data)
        data.setdefault("form", {})
        data["form"].update(self.read(["partner_ids"])[0])
        return data

    def action_view_partner_ledger(self):
        self.ensure_one()
        self._validate_partner_ledger_dates()
        return {
            "type": "ir.actions.act_window",
            "name": _("Partner Ledger Entries"),
            "res_model": "account.move.line",
            "view_mode": "tree,form",
            "domain": self._partner_ledger_domain(),
            "context": {
                "create": False,
                "edit": False,
                "group_by": "partner_id",
            },
        }

    def action_export_partner_ledger_xlsx(self):
        self.ensure_one()
        self._validate_partner_ledger_dates()
        if xlsxwriter is None:
            raise UserError(_("The xlsxwriter Python package is required to export Excel files."))

        move_lines = self.env["account.move.line"].search(
            self._partner_ledger_domain(),
            order="partner_id, date, move_name, id",
        )

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(_("Partner Ledger")[:31])

        title_format = workbook.add_format({"bold": True, "font_size": 14})
        header_format = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
        text_format = workbook.add_format({"border": 1})
        money_format = workbook.add_format({"num_format": "#,##0.00", "border": 1})

        sheet.merge_range(0, 0, 0, 8, _("Partner Ledger"), title_format)
        sheet.write(1, 0, _("Company"), header_format)
        sheet.write(1, 1, self.company_id.display_name or "", text_format)
        sheet.write(2, 0, _("Period"), header_format)
        sheet.write(2, 1, "%s - %s" % (self.date_from or "", self.date_to or ""), text_format)
        sheet.write(3, 0, _("Partners"), header_format)
        sheet.write(3, 1, ", ".join(self.partner_ids.mapped("display_name")) if self.partner_ids else _("All"), text_format)

        headers = [
            _("Date"),
            _("Journal"),
            _("Move"),
            _("Partner"),
            _("Account"),
            _("Label"),
            _("Debit"),
            _("Credit"),
            _("Balance"),
        ]
        row = 5
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)

        running_balance_by_partner = {}
        for line in move_lines:
            row += 1
            partner_key = line.partner_id.id or 0
            running_balance_by_partner[partner_key] = running_balance_by_partner.get(partner_key, 0.0) + line.balance
            sheet.write(row, 0, line.date and line.date.strftime("%Y-%m-%d") or "", text_format)
            sheet.write(row, 1, line.journal_id.code or line.journal_id.display_name or "", text_format)
            sheet.write(row, 2, line.move_id.name or line.move_name or "", text_format)
            sheet.write(row, 3, line.partner_id.display_name or "", text_format)
            sheet.write(row, 4, line.account_id.display_name or "", text_format)
            sheet.write(row, 5, line.name or line.ref or line.move_id.ref or "", text_format)
            sheet.write_number(row, 6, line.debit or 0.0, money_format)
            sheet.write_number(row, 7, line.credit or 0.0, money_format)
            sheet.write_number(row, 8, running_balance_by_partner[partner_key], money_format)

        row += 2
        sheet.write(row, 5, _("Total"), header_format)
        sheet.write_number(row, 6, sum(move_lines.mapped("debit")), money_format)
        sheet.write_number(row, 7, sum(move_lines.mapped("credit")), money_format)
        sheet.write_number(row, 8, sum(move_lines.mapped("balance")), money_format)

        sheet.freeze_panes(6, 0)
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 5, 22)
        sheet.set_column(6, 8, 14)
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
