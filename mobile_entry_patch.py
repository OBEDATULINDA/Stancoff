"""Mobile-first Stancoff data entry, using existing authenticated ERP workflows."""
from datetime import date
from flask import abort, redirect, render_template, session, url_for
import app as erp

def register_mobile_entry(app):
    @app.route("/mobile")
    @erp.login_required
    def mobile_home():
        company = erp.current_company()
        if not company or not company.is_legacy_stancoff:
            return redirect(url_for("company_dashboard"))
        role = session.get("role", "Viewer")
        allowed = erp.ROLE_PERMISSIONS.get(role, set())
        def can(permission):
            return "*" in allowed or permission in allowed
        return render_template(
            "mobile_entry.html", today=date.today().isoformat(),
            can_purchase=can("purchases"), can_batch=can("batches"),
            can_processing=can("processing"), can_drying=can("drying"),
            can_inventory=can("inventory"), can_transfers=can("transfers"),
            batches=erp.Batch.query.order_by(erp.Batch.id.desc()).limit(100).all() if can("purchases") else [],
            suppliers=erp.Supplier.query.order_by(erp.Supplier.name).all() if can("purchases") else [],
            next_batch=erp.next_code(erp.Batch,"batch_no","STA",3) if can("batches") else "",
        )
