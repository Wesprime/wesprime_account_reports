from odoo import api, models


class ReportWesprimeDailyTransactionSummary(models.AbstractModel):
    _name = "report.wesprime_account_reports.report_daily_transaction_summary_pdf"
    _description = "Wesprime Daily Transaction Summary PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["wesprime.daily.transaction.summary.wizard"].browse(docids)
        for wizard in docs:
            if not wizard.result_line_ids:
                wizard._generate_lines()
        return {
            "doc_ids": docids,
            "doc_model": "wesprime.daily.transaction.summary.wizard",
            "docs": docs,
        }
