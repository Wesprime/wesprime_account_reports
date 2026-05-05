from odoo import api, models


class ReportWesprimePartnerLedger(models.AbstractModel):
    _name = "report.wesprime_account_reports.report_partner_ledger_pdf"
    _description = "Wesprime Partner Ledger PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["wesprime.partner.ledger.wizard"].browse(docids)
        for wizard in docs:
            if not wizard.result_line_ids:
                wizard._generate_lines()
        return {
            "doc_ids": docids,
            "doc_model": "wesprime.partner.ledger.wizard",
            "docs": docs,
        }
