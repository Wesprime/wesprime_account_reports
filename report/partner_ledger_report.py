from odoo import api, models


class ReportPartnerLedger(models.AbstractModel):
    _inherit = "report.base_accounting_kit.report_partnerledger"

    @api.model
    def _get_report_values(self, docids, data=None):
        values = super()._get_report_values(docids, data=data)
        partner_ids = data and data.get("form", {}).get("partner_ids")
        if partner_ids:
            selected_partners = self.env["res.partner"].browse(partner_ids)
            if values.get("docs"):
                values["docs"] = values["docs"] & selected_partners
            values["doc_ids"] = selected_partners.ids
        return values
