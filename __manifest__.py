{
    "name": "Wesprime Account Reports",
    "summary": "Community accounting reports, daily summaries, and dashboard",
    "version": "17.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "Wesprime",
    "license": "LGPL-3",
    "depends": ["account", "base_accounting_kit", "web"],
    "data": [
        "security/ir.model.access.csv",
        "data/cleanup_partner_ledger.xml",
        "report/aged_partner_balance_report.xml",
        "report/daily_transaction_summary_report.xml",
        "views/aged_partner_balance_views.xml",
        "views/partner_ledger_views.xml",
        "views/daily_transaction_summary_views.xml",
        "views/reporting_dashboard_views.xml",
        "views/menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "wesprime_account_reports/static/src/scss/dashboard.scss",
        ],
    },
    "installable": True,
    "application": False,
}
