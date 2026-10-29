"""Mobile-first Stancoff data entry, using existing authenticated ERP workflows."""
from datetime import date, timedelta
from sqlalchemy import func
from flask import abort, redirect, render_template, session, url_for, request, flash
import app as erp

def register_mobile_entry(app):
    @app.route("/mobile")
    def mobile_home():
        if "user_id" not in session:
            return redirect(url_for("mobile_login"))
        company = erp.current_company()
        if not company:
            return redirect(url_for("mobile_company_select"))
        if not company.is_legacy_stancoff:
            return redirect(url_for("mobile_company_workspace"))
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

    @app.route("/mobile/batches")
    @erp.permission_required("batches")
    def mobile_batches():
        return render_template("mobile_records.html", title="Coffee batches", kind="batches",
            rows=erp.Batch.query.order_by(erp.Batch.id.desc()).limit(300).all())

    @app.route("/mobile/batches/<int:batch_id>")
    @erp.permission_required("batches")
    def mobile_batch_detail(batch_id):
        batch=erp.db.get_or_404(erp.Batch,batch_id)
        purchases=erp.Purchase.query.filter_by(batch_id=batch_id).order_by(erp.Purchase.id.desc()).all()
        processing=erp.Processing.query.filter_by(batch_id=batch_id).order_by(erp.Processing.id.desc()).all()
        drying=erp.Drying.query.filter_by(batch_id=batch_id).order_by(erp.Drying.id.desc()).all()
        stocks=erp.CoffeeStock.query.filter_by(batch_id=batch_id).order_by(erp.CoffeeStock.id.desc()).all()
        movements=erp.CoffeeMovement.query.filter_by(batch_id=batch_id).order_by(erp.CoffeeMovement.id.desc()).all()
        active=[p for p in purchases if p.status!="Voided"]
        return render_template("mobile_batch_detail.html",batch=batch,purchases=purchases,processing=processing,
            drying=drying,stocks=stocks,movements=movements,
            gross_weight=sum(float(p.gross_weight or 0) for p in active),
            good_weight=sum(float(p.good_weight or 0) for p in active),
            purchase_total=sum(float(p.total_amount or 0) for p in active))

    @app.route("/mobile/records/<kind>")
    @erp.login_required
    def mobile_records(kind):
        configs={
            "purchases":("purchases",erp.Purchase,"Coffee purchases"),
            "processing":("processing",erp.Processing,"Processing records"),
            "drying":("drying",erp.Drying,"Drying records"),
            "inventory":("inventory",erp.CoffeeStock,"Coffee inventory"),
            "transfers":("transfers",erp.StationTransferDocument,"Station transfers"),
        }
        if kind not in configs:
            abort(404)
        permission,model,title=configs[kind]
        role=session.get("role","Viewer")
        allowed=erp.ROLE_PERMISSIONS.get(role,set())
        if "*" not in allowed and permission not in allowed:
            abort(403)
        if kind=="inventory":
            erp.ensure_initial_stock()
        return render_template("mobile_records.html",title=title,kind=kind,
            rows=model.query.order_by(model.id.desc()).limit(250).all())

    @app.route("/mobile/companies")
    def mobile_company_select():
        if "user_id" not in session:
            return redirect(url_for("mobile_login"))
        companies=erp.available_companies_for_user(session["user_id"])
        return render_template("mobile_companies.html",companies=companies)

    @app.route("/mobile/companies/<int:company_id>/select",methods=["POST"])
    def mobile_select_company(company_id):
        if "user_id" not in session:
            return redirect(url_for("mobile_login"))
        company=erp.db.session.get(erp.Company,company_id)
        if not company or company.status!="Active":
            flash("That company is not available.")
            return redirect(url_for("mobile_company_select"))
        membership=erp.company_membership(session["user_id"],company.id)
        if not membership and not erp.user_is_super_admin():
            abort(403)
        user=erp.db.session.get(erp.User,session["user_id"])
        session["company_id"]=company.id
        session["company_name"]=company.name
        session["company_slug"]=company.slug
        session["role"]=membership.role if membership else "Admin"
        session["system_role"]=user.role if user else "Viewer"
        erp.log_action("SELECT","Company",company.id,f"Opened {company.name} on mobile")
        return redirect(url_for("mobile_home") if company.is_legacy_stancoff else url_for("mobile_company_workspace"))

    @app.route("/mobile/company")
    def mobile_company_workspace():
        if "user_id" not in session:
            return redirect(url_for("mobile_login"))
        company=erp.current_company()
        if not company:
            return redirect(url_for("mobile_company_select"))
        if company.is_legacy_stancoff:
            return redirect(url_for("mobile_home"))
        modules=erp.enabled_company_modules(company.id)
        return render_template("mobile_company_workspace.html",company=company,modules=modules,
            commercial_coffee=erp._company_has_commercial_coffee(company))

    @app.route("/mobile/login", methods=["GET","POST"])
    def mobile_login():
        if request.method=="GET":
            if "user_id" in session:
                return redirect(url_for("mobile_company_select"))
            return render_template("login.html",mobile_login_action=True)
        response=erp.login()
        if "user_id" in session:
            return redirect(url_for("mobile_company_select"))
        return response

    @app.route("/mobile/logout")
    def mobile_logout():
        erp.log_action("LOGOUT","Authentication")
        session.clear()
        return redirect(url_for("mobile_login"))
