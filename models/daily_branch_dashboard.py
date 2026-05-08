from odoo import api, fields, models


class WesprimeBranchRef(models.Model):
    _name = "wesprime.branch.ref"
    _description = "Wesprime Branch Reference"
    _order = "name, id"

    name = fields.Char(required=True)
    source_model = fields.Char(required=True, index=True)
    source_res_id = fields.Integer(required=True, index=True)
    company_id = fields.Many2one("res.company", index=True)

    _sql_constraints = [
        (
            "branch_ref_source_uniq",
            "unique(source_model, source_res_id, company_id)",
            "This branch reference already exists for the company.",
        )
    ]

    @api.model
    def get_or_create_ref(self, source_model, source_res_id, name, company):
        company_id = company.id if company else False
        source_res_id = source_res_id or 0
        domain = [
            ("source_model", "=", source_model),
            ("source_res_id", "=", source_res_id),
            ("company_id", "=", company_id),
        ]
        ref = self.search(domain, limit=1)
        vals = {
            "name": name or source_model,
            "source_model": source_model,
            "source_res_id": source_res_id,
            "company_id": company_id,
        }
        if ref:
            if ref.name != vals["name"]:
                ref.write({"name": vals["name"]})
            return ref
        return self.create(vals)
