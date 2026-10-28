"""Mobile-first Stancoff data entry, using existing authenticated ERP workflows."""
from datetime import date, timedelta
from sqlalchemy import func
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
        erp.ensure_initial_stock()
        stocks = erp.CoffeeStock.query.join(erp.Location).filter(erp.CoffeeStock.weight > 0.0001, erp.Location.station_id.isnot(None)).order_by(erp.CoffeeStock.updated_at.desc()).all() if can("transfers") else []
        processes = erp.Processing.query.filter_by(status="Active").order_by(erp.Processing.id.desc()).limit(200).all() if can("drying") else []
        today_purchases = erp.Purchase.query.filter(erp.Purchase.status=="Active", erp.Purchase.purchase_date==date.today()).all()
        active_stocks = erp.CoffeeStock.query.filter(erp.CoffeeStock.weight>0).all()
        year = date.today().year
        yearly_purchases = erp.Purchase.query.filter(erp.Purchase.status=="Active", erp.Purchase.purchase_date>=date(year,1,1), erp.Purchase.purchase_date<date(year+1,1,1)).all()
        monthly_kg = [0.0] * 12
        for purchase in yearly_purchases:
            monthly_kg[purchase.purchase_date.month-1] += float(purchase.good_weight or 0)
        total_purchased_kg = erp.db.session.query(func.coalesce(func.sum(erp.Purchase.good_weight),0)).filter(erp.Purchase.status=="Active").scalar() or 0
        warehouse_dried_kg = sum(float(s.weight or 0) for s in active_stocks if s.location and s.location.location_type=="Final Warehouse")
        return render_template(
            "mobile_entry.html", today=date.today().isoformat(),
            username=session.get("username","User"),
            purchase_year=year, purchase_monthly_kg=[round(v,2) for v in monthly_kg],
            purchased_year_kg=sum(monthly_kg), total_purchased_kg=float(total_purchased_kg),
            warehouse_dried_kg=warehouse_dried_kg,
            today_kg=sum(float(p.good_weight or 0) for p in today_purchases),
            today_spend=sum(float(p.total_amount or 0) for p in today_purchases),
            stock_kg=sum(float(s.weight or 0) for s in active_stocks),
            open_batches=erp.Batch.query.filter(erp.Batch.status.in_(["Open","Processing","Drying"])).count(),
            active_drying=erp.Drying.query.filter(erp.Drying.status=="Active",erp.Drying.drying_status!="Completed").count(),
            pending_transfers=erp.StationTransferDocument.query.filter_by(status="In Transit").count(),
            recent_purchases=erp.Purchase.query.filter_by(status="Active").order_by(erp.Purchase.id.desc()).limit(5).all(),
            stations=erp.Station.query.filter_by(status="Active").order_by(erp.Station.name).all() if can("processing") else [],
            processes=processes,
            grade_weights={str(p.id):{"Grade A":float(p.grade_a_weight or 0),"Grade B":float(p.grade_b_weight or 0),"Grade C":float(p.grade_c_weight or 0)} for p in processes},
            drying_locations=erp.Location.query.join(erp.Station).filter(erp.Location.status=="Active",erp.Location.location_type=="Drying Area",erp.Station.status=="Active").order_by(erp.Station.name,erp.Location.name).all() if can("drying") else [],
            stocks=stocks,
            destinations=erp.Location.query.join(erp.Station).filter(erp.Location.status=="Active",erp.Station.status=="Active").order_by(erp.Station.name,erp.Location.name).all() if can("transfers") else [],
            can_purchase=can("purchases"), can_batch=can("batches"),
            can_processing=can("processing"), can_drying=can("drying"),
            can_inventory=can("inventory"), can_transfers=can("transfers"),
            batches=erp.Batch.query.order_by(erp.Batch.id.desc()).limit(100).all() if (can("purchases") or can("processing") or can("batches")) else [],
            suppliers=erp.Supplier.query.order_by(erp.Supplier.name).all() if can("purchases") else [],
            next_batch=erp.next_code(erp.Batch,"batch_no","STA",3) if can("batches") else "",
        )
