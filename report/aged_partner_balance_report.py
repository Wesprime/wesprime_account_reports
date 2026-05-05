from odoo import api, models


class ReportWesprimeAgedPartnerBalance(models.AbstractModel):
    _name = "report.wesprime_account_reports.report_aged_partner_balance_pdf"
    _description = "Wesprime Aged Partner Balance PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["wesprime.aged.partner.balance.wizard"].browse(docids)
        for wizard in docs:
            if not wizard.result_line_ids:
                wizard._generate_lines()
        return {
            "doc_ids": docids,
            "doc_model": "wesprime.aged.partner.balance.wizard",
            "docs": docs,
        }
