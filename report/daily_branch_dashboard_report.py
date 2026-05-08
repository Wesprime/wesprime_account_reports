from odoo import api, models


class ReportWesprimeDailyBranchDashboardPdf(models.AbstractModel):
    _name = "report.war.branch_dash_pdf"
    _description = "Daily Branch Control Dashboard PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["wesprime.daily.branch.dashboard"].browse(docids)
        for dashboard in docs:
            if not dashboard.summary_line_ids:
                dashboard._refresh_dashboard_lines()
        return {
            "doc_ids": docids,
            "doc_model": "wesprime.daily.branch.dashboard",
            "docs": docs,
        }
