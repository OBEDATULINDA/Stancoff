"""Application entrypoint adding dashboard custom-period reporting to stable bootstrap."""
from bootstrap import app
import app as stancoff
from dashboard_filter_patch import register_dashboard_filter

register_dashboard_filter(app, stancoff)

from purchase_reports_patch import register_purchase_reports
register_purchase_reports(app, stancoff)

from report_center_patch import register_report_center
register_report_center(app, stancoff)
