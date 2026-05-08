import base64
import io

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - handled inside Odoo
    xlsxwriter = None

from odoo import _, models
from odoo.exceptions import UserError


class ReportWesprimeDailyBranchDashboardXlsx(models.AbstractModel):
    _name = "report.war.branch_dash_xlsx"
    _description = "Daily Branch Control Dashboard XLSX"

    def _write_table(self, workbook, sheet, headers, rows):
        header_format = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
        text_format = workbook.add_format({"border": 1})
        number_format = workbook.add_format({"num_format": "#,##0.00", "border": 1})
        integer_format = workbook.add_format({"num_format": "#,##0", "border": 1})

        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)

        for row_index, row_values in enumerate(rows, start=1):
            for col, value in enumerate(row_values):
                if isinstance(value, int):
                    sheet.write_number(row_index, col, value, integer_format)
                elif isinstance(value, float):
                    sheet.write_number(row_index, col, value, number_format)
                else:
                    sheet.write(row_index, col, value or "", text_format)

        sheet.freeze_panes(1, 0)
        for col, header in enumerate(headers):
            sheet.set_column(col, col, max(14, min(32, len(header) + 4)))

    def _product_group_label(self, line):
        return dict(line._fields["product_group"].selection).get(line.product_group, line.product_group or "")

    def _create_xlsx_attachment(self, dashboard):
        dashboard.ensure_one()
        if xlsxwriter is None:
            raise UserError(_("The xlsxwriter Python package is required to export Excel files."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})

        self._write_table(
            workbook,
            workbook.add_worksheet(_("Summary")),
            [
                _("Branch"),
                _("Date"),
                _("Sales Qty"),
                _("Sales Value"),
                _("Cash Sales"),
                _("Bank/UPI Sales"),
                _("Credit Sales"),
                _("Cash Difference"),
                _("New Credit"),
                _("Total Outstanding"),
                _("Overdue Customers"),
            ],
            [
                [
                    line.branch_ref_id.display_name,
                    line.date and line.date.strftime("%Y-%m-%d"),
                    line.sales_quantity,
                    line.sales_value,
                    line.cash_sales,
                    line.bank_sales,
                    line.credit_sales,
                    line.cash_difference,
                    line.new_credit,
                    line.total_outstanding,
                    line.overdue_customer_count,
                ]
                for line in dashboard.summary_line_ids
            ],
        )
        self._write_table(
            workbook,
            workbook.add_worksheet(_("Sales Summary")),
            [_("Branch"), _("Date"), _("Product Group"), _("Quantity"), _("Value")],
            [
                [
                    line.branch_ref_id.display_name,
                    line.date and line.date.strftime("%Y-%m-%d"),
                    self._product_group_label(line),
                    line.quantity,
                    line.value,
                ]
                for line in dashboard.sales_line_ids
            ],
        )
        self._write_table(
            workbook,
            workbook.add_worksheet(_("Payment Split")),
            [_("Branch"), _("Date"), _("Cash Sales"), _("Bank/UPI Sales"), _("Credit Sales")],
            [
                [
                    line.branch_ref_id.display_name,
                    line.date and line.date.strftime("%Y-%m-%d"),
                    line.cash_sales,
                    line.bank_sales,
                    line.credit_sales,
                ]
                for line in dashboard.payment_line_ids
            ],
        )
        self._write_table(
            workbook,
            workbook.add_worksheet(_("Cash Control")),
            [
                _("Branch"),
                _("Date"),
                _("Opening Cash"),
                _("Cash Sales"),
                _("Expenses"),
                _("Expected Closing"),
                _("Actual Closing"),
                _("Difference"),
            ],
            [
                [
                    line.branch_ref_id.display_name,
                    line.date and line.date.strftime("%Y-%m-%d"),
                    line.opening_cash,
                    line.cash_sales_system,
                    line.expenses_system,
                    line.closing_cash_expected,
                    line.actual_closing_cash,
                    line.difference,
                ]
                for line in dashboard.cash_line_ids
            ],
        )
        self._write_table(
            workbook,
            workbook.add_worksheet(_("Bank Control")),
            [_("Branch"), _("Date"), _("System Bank/UPI"), _("Bank Statement"), _("Difference")],
            [
                [
                    line.branch_ref_id.display_name,
                    line.date and line.date.strftime("%Y-%m-%d"),
                    line.bank_sales_system,
                    line.bank_statement_total,
                    line.bank_difference,
                ]
                for line in dashboard.bank_line_ids
            ],
        )
        self._write_table(
            workbook,
            workbook.add_worksheet(_("Credit Control")),
            [
                _("Branch"),
                _("Date"),
                _("New Credit"),
                _("Total Outstanding"),
                _("Overdue Amount"),
                _("Overdue Customers"),
                _("Customer Names"),
            ],
            [
                [
                    line.branch_ref_id.display_name,
                    line.date and line.date.strftime("%Y-%m-%d"),
                    line.new_credit,
                    line.total_outstanding,
                    line.overdue_amount,
                    line.overdue_customer_count,
                    line.overdue_customer_names,
                ]
                for line in dashboard.credit_line_ids
            ],
        )
        self._write_table(
            workbook,
            workbook.add_worksheet(_("Inventory Snapshot")),
            [
                _("Branch"),
                _("Date"),
                _("Product Group"),
                _("Opening Stock"),
                _("Received"),
                _("Sold"),
                _("Closing Stock"),
                _("Note"),
            ],
            [
                [
                    line.branch_ref_id.display_name,
                    line.date and line.date.strftime("%Y-%m-%d"),
                    self._product_group_label(line),
                    line.opening_stock,
                    line.received,
                    line.sold,
                    line.closing_stock,
                    line.note,
                ]
                for line in dashboard.inventory_line_ids
            ],
        )

        workbook.close()
        return self.env["ir.attachment"].create(
            {
                "name": "daily_branch_control_dashboard.xlsx",
                "type": "binary",
                "datas": base64.b64encode(output.getvalue()),
                "res_model": dashboard._name,
                "res_id": dashboard.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
