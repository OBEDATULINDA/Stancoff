
import os
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, desc
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-in-production")
database_url = os.getenv("DATABASE_URL", "sqlite:///stancoff.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

ROLE_PERMISSIONS = {
    "Admin": {"*"},
    "Manager": {"dashboard","suppliers","prices","batches","purchases","processing","drying","inventory","locations","sales","dispatch","casuals","rates","attendance","payments","reports"},
    "Receiving Clerk": {"dashboard","suppliers","batches","purchases"},
    "Processing Supervisor": {"dashboard","batches","processing","drying","inventory","locations","reports"},
    "Storekeeper": {"dashboard","batches","drying","inventory","locations","sales","dispatch","reports"},
    "Payroll Officer": {"dashboard","casuals","rates","attendance","payments"},
    "Viewer": {"dashboard","reports"},
}

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="Viewer")
    status = db.Column(db.String(20), nullable=False, default="Active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    username = db.Column(db.String(80))
    action = db.Column(db.String(80), nullable=False)
    module = db.Column(db.String(80), nullable=False)
    record_id = db.Column(db.String(80))
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(50))
    location = db.Column(db.String(150))
    status = db.Column(db.String(20), default="Active")

class PriceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    effective_date = db.Column(db.Date, nullable=False)
    cherry_price = db.Column(db.Float, nullable=False)
    floater_price = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text)

class Batch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    batch_no = db.Column(db.String(20), unique=True, nullable=False)
    batch_date = db.Column(db.Date, nullable=False)
    process_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(30), default="Open")
    notes = db.Column(db.Text)

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    receipt_no = db.Column(db.String(30), unique=True, nullable=False)
    purchase_date = db.Column(db.Date, nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("batch.id"), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("supplier.id"), nullable=False)
    gross_weight = db.Column(db.Float, nullable=False)
    floaters_weight = db.Column(db.Float, default=0)
    good_weight = db.Column(db.Float, nullable=False)
    floaters_bought = db.Column(db.String(10), nullable=False)
    cherry_price = db.Column(db.Float, nullable=False)
    floater_price = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default="Active")
    void_reason = db.Column(db.Text)
    created_by = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    batch = db.relationship("Batch")
    supplier = db.relationship("Supplier")

class Processing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    processing_no = db.Column(db.String(30), unique=True, nullable=False)
    processing_date = db.Column(db.Date, nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("batch.id"), nullable=False, unique=True)
    input_weight = db.Column(db.Float, nullable=False)
    grade_a_weight = db.Column(db.Float, nullable=False, default=0)
    grade_b_weight = db.Column(db.Float, nullable=False, default=0)
    grade_c_weight = db.Column(db.Float, nullable=False, default=0)
    total_sorted_weight = db.Column(db.Float, nullable=False, default=0)
    processing_loss = db.Column(db.Float, nullable=False, default=0)
    outturn_percent = db.Column(db.Float, nullable=False, default=0)
    moisture = db.Column(db.Float)
    processed_by = db.Column(db.String(120))
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="Active")
    void_reason = db.Column(db.Text)
    created_by = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    batch = db.relationship("Batch")

class Drying(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    drying_no = db.Column(db.String(30), unique=True, nullable=False)
    processing_id = db.Column(db.Integer, db.ForeignKey("processing.id"), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("batch.id"), nullable=False)
    grade = db.Column(db.String(20), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    input_weight = db.Column(db.Float, nullable=False)
    dry_weight = db.Column(db.Float)
    drying_loss = db.Column(db.Float, nullable=False, default=0)
    outturn_percent = db.Column(db.Float, nullable=False, default=0)
    moisture = db.Column(db.Float)
    drying_location = db.Column(db.String(150))
    dried_by = db.Column(db.String(120))
    drying_status = db.Column(db.String(20), nullable=False, default="Drying")
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="Active")
    void_reason = db.Column(db.Text)
    created_by = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    processing = db.relationship("Processing")
    batch = db.relationship("Batch")

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    location_type = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Active")
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CoffeeStock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    drying_id = db.Column(db.Integer, db.ForeignKey("drying.id"), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("batch.id"), nullable=False)
    grade = db.Column(db.String(20), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey("location.id"), nullable=False)
    weight = db.Column(db.Float, nullable=False, default=0)
    moisture = db.Column(db.Float)
    stock_status = db.Column(db.String(30), nullable=False, default="Drying")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    drying = db.relationship("Drying")
    batch = db.relationship("Batch")
    location = db.relationship("Location")
    __table_args__ = (db.UniqueConstraint("drying_id", "location_id", name="uq_stock_drying_location"),)

class CoffeeMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    movement_no = db.Column(db.String(30), unique=True, nullable=False)
    drying_id = db.Column(db.Integer, db.ForeignKey("drying.id"), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("batch.id"), nullable=False)
    grade = db.Column(db.String(20), nullable=False)
    from_location_id = db.Column(db.Integer, db.ForeignKey("location.id"), nullable=False)
    to_location_id = db.Column(db.Integer, db.ForeignKey("location.id"), nullable=False)
    movement_date = db.Column(db.Date, nullable=False)
    weight = db.Column(db.Float, nullable=False)
    moisture = db.Column(db.Float)
    movement_type = db.Column(db.String(40), nullable=False)
    reason = db.Column(db.Text)
    moved_by = db.Column(db.String(120))
    status = db.Column(db.String(20), nullable=False, default="Active")
    void_reason = db.Column(db.Text)
    created_by = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    drying = db.relationship("Drying")
    batch = db.relationship("Batch")
    from_location = db.relationship("Location", foreign_keys=[from_location_id])
    to_location = db.relationship("Location", foreign_keys=[to_location_id])

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_no = db.Column(db.String(30), unique=True, nullable=False)
    sale_date = db.Column(db.Date, nullable=False)
    buyer_name = db.Column(db.String(180), nullable=False)
    buyer_phone = db.Column(db.String(60))
    destination = db.Column(db.String(220), nullable=False)
    contract_ref = db.Column(db.String(80))
    contracted_weight = db.Column(db.Float, nullable=False, default=0)
    price_per_kg = db.Column(db.Float, nullable=False, default=0)
    total_value = db.Column(db.Float, nullable=False, default=0)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="Open")
    void_reason = db.Column(db.Text)
    created_by = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Dispatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dispatch_no = db.Column(db.String(30), unique=True, nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey("sale.id"), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey("coffee_stock.id"), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("batch.id"), nullable=False)
    grade = db.Column(db.String(20), nullable=False)
    from_location_id = db.Column(db.Integer, db.ForeignKey("location.id"), nullable=False)
    dispatch_date = db.Column(db.Date, nullable=False)
    weight = db.Column(db.Float, nullable=False)
    number_of_bags = db.Column(db.Integer)
    bag_size = db.Column(db.Float)
    moisture = db.Column(db.Float)
    vehicle_no = db.Column(db.String(80))
    driver_name = db.Column(db.String(150))
    driver_phone = db.Column(db.String(60))
    destination = db.Column(db.String(220), nullable=False)
    reason = db.Column(db.Text)
    dispatched_by = db.Column(db.String(120))
    status = db.Column(db.String(20), nullable=False, default="Active")
    void_reason = db.Column(db.Text)
    created_by = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sale = db.relationship("Sale")
    stock = db.relationship("CoffeeStock")
    batch = db.relationship("Batch")
    from_location = db.relationship("Location")

class Casual(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    sex = db.Column(db.String(20))
    phone = db.Column(db.String(50))
    status = db.Column(db.String(20), default="Active")

class CasualRate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    casual_id = db.Column(db.Integer, db.ForeignKey("casual.id"), nullable=False)
    effective_date = db.Column(db.Date, nullable=False)
    daily_rate = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text)
    casual = db.relationship("Casual")

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_date = db.Column(db.Date, nullable=False)
    casual_id = db.Column(db.Integer, db.ForeignKey("casual.id"), nullable=False)
    work_done = db.Column(db.String(180))
    work_type = db.Column(db.String(30), nullable=False)
    rate = db.Column(db.Float, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default="Unpaid")
    payment_ref = db.Column(db.String(30))
    casual = db.relationship("Casual")

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    payment_ref = db.Column(db.String(30), unique=True, nullable=False)
    casual_id = db.Column(db.Integer, db.ForeignKey("casual.id"), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    gross_pay = db.Column(db.Float, nullable=False)
    deduction = db.Column(db.Float, default=0)
    net_paid = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    method = db.Column(db.String(30))
    status = db.Column(db.String(20), default="Paid")
    void_reason = db.Column(db.Text)
    casual = db.relationship("Casual")

def log_action(action, module, record_id=None, details=None):
    if "user_id" not in session:
        return
    db.session.add(AuditLog(
        user_id=session["user_id"],
        username=session.get("username"),
        action=action,
        module=module,
        record_id=str(record_id) if record_id else None,
        details=details
    ))
    db.session.commit()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def permission_required(permission):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            role = session.get("role", "Viewer")
            allowed = ROLE_PERMISSIONS.get(role, set())
            if "*" not in allowed and permission not in allowed:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def next_code(model, field, prefix, width):
    row = model.query.order_by(model.id.desc()).first()
    if not row:
        return f"{prefix}{1:0{width}d}"
    old = getattr(row, field)
    try:
        n = int(old.replace(prefix, "")) + 1
    except Exception:
        n = 1
    return f"{prefix}{n:0{width}d}"

def get_price(d):
    return PriceHistory.query.filter(PriceHistory.effective_date <= d).order_by(
        PriceHistory.effective_date.desc(), PriceHistory.id.desc()).first()

def get_rate(casual_id, d):
    return CasualRate.query.filter(
        CasualRate.casual_id == casual_id,
        CasualRate.effective_date <= d
    ).order_by(CasualRate.effective_date.desc(), CasualRate.id.desc()).first()

@app.before_request
def ensure_db():
    db.create_all()
    if not User.query.first():
        admin_user = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
        db.session.add(User(
            full_name="System Administrator",
            username=admin_user,
            password_hash=generate_password_hash(admin_password),
            role="Admin",
            status="Active"
        ))
        db.session.commit()

@app.context_processor
def inject_helpers():
    return {"current_role": session.get("role"), "current_user": session.get("full_name")}

@app.route("/health")
def health():
    return {"status": "ok", "service": "stancoff"}, 200

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()
        if not user or user.status != "Active" or not check_password_hash(user.password_hash, request.form["password"]):
            flash("Invalid username or password.")
            return render_template("login.html")
        session.clear()
        session.update(user_id=user.id, username=user.username, full_name=user.full_name, role=user.role)
        user.last_login = datetime.utcnow()
        db.session.commit()
        log_action("LOGIN", "Authentication", user.id)
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    log_action("LOGOUT", "Authentication")
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    """Operations dashboard using Python aggregation for PostgreSQL/SQLite compatibility."""
    period = request.args.get("period", "90")
    period_days = {"30": 30, "90": 90, "365": 365}
    start_date = None
    if period in period_days:
        start_date = datetime.utcnow().date() - timedelta(days=period_days[period] - 1)
    elif period != "all":
        period = "90"
        start_date = datetime.utcnow().date() - timedelta(days=89)

    all_active_purchases = Purchase.query.filter_by(status="Active").order_by(Purchase.purchase_date.asc()).all()
    active_purchases = [p for p in all_active_purchases if not start_date or p.purchase_date >= start_date]
    all_processing = Processing.query.filter_by(status="Active").order_by(Processing.processing_date.asc()).all()
    processing_rows = [r for r in all_processing if not start_date or r.processing_date >= start_date]
    all_drying = Drying.query.filter_by(status="Active").order_by(Drying.start_date.asc()).all()
    drying_rows = [r for r in all_drying if not start_date or r.start_date >= start_date]
    stock_rows = CoffeeStock.query.filter(CoffeeStock.weight > 0).all()
    movement_rows = CoffeeMovement.query.filter_by(status="Active").order_by(CoffeeMovement.movement_date.asc()).all()
    period_movements = [m for m in movement_rows if not start_date or m.movement_date >= start_date]

    total_good = sum(float(p.good_weight or 0) for p in active_purchases)
    total_spend = sum(float(p.total_amount or 0) for p in active_purchases)
    current_stock = sum(float(s.weight or 0) for s in stock_rows)
    completed_drying = [r for r in drying_rows if r.drying_status == "Completed" and r.dry_weight is not None]
    processing_outturns = [float(r.outturn_percent or 0) for r in processing_rows if float(r.input_weight or 0) > 0]
    drying_outturns = [float(r.outturn_percent or 0) for r in completed_drying if float(r.input_weight or 0) > 0]

    stock_by_type = {"Drying Area": 0.0, "Temporary Storage": 0.0, "Final Warehouse": 0.0}
    grade_inventory = {"Grade A": 0.0, "Grade B": 0.0, "Grade C": 0.0}
    location_inventory = {}
    status_inventory = {}
    for stock in stock_rows:
        weight = float(stock.weight or 0)
        grade_inventory[stock.grade] = grade_inventory.get(stock.grade, 0.0) + weight
        location_name = stock.location.name if stock.location else "Unknown"
        location_inventory[location_name] = location_inventory.get(location_name, 0.0) + weight
        location_type = stock.location.location_type if stock.location else "Unknown"
        stock_by_type[location_type] = stock_by_type.get(location_type, 0.0) + weight
        status_inventory[stock.stock_status] = status_inventory.get(stock.stock_status, 0.0) + weight

    stats = {
        "suppliers": Supplier.query.filter_by(status="Active").count(),
        "open_batches": Batch.query.filter(Batch.status.in_(["Open", "Processing", "Drying"])).count(),
        "purchases": len(active_purchases),
        "good_weight": total_good,
        "total_spend": total_spend,
        "current_stock": current_stock,
        "temporary_stock": stock_by_type.get("Temporary Storage", 0.0),
        "final_stock": stock_by_type.get("Final Warehouse", 0.0),
        "drying_stock": stock_by_type.get("Drying Area", 0.0),
        "processing_outturn": sum(processing_outturns) / len(processing_outturns) if processing_outturns else 0,
        "drying_outturn": sum(drying_outturns) / len(drying_outturns) if drying_outturns else 0,
        "movements": len(period_movements),
    }

    supplier_totals = {}
    area_totals = {}
    monthly_totals = {}
    process_totals = {}
    for p in active_purchases:
        weight = float(p.good_weight or 0)
        value = float(p.total_amount or 0)
        supplier = p.supplier
        batch = p.batch

        supplier_key = supplier.id
        row = supplier_totals.setdefault(supplier_key, {
            "name": supplier.name, "code": supplier.code, "weight": 0.0,
            "deliveries": 0, "value": 0.0,
        })
        row["weight"] += weight
        row["deliveries"] += 1
        row["value"] += value

        area = (supplier.location or "").strip() or "Unspecified"
        area_row = area_totals.setdefault(area, {"area": area, "weight": 0.0, "deliveries": 0})
        area_row["weight"] += weight
        area_row["deliveries"] += 1

        month = p.purchase_date.strftime("%Y-%m")
        month_row = monthly_totals.setdefault(month, {"month": month, "weight": 0.0, "value": 0.0})
        month_row["weight"] += weight
        month_row["value"] += value

        process_name = batch.process_type or "Unspecified"
        process_totals[process_name] = process_totals.get(process_name, 0.0) + weight

    top_suppliers = sorted(supplier_totals.values(), key=lambda r: r["weight"], reverse=True)[:8]
    area_rows = sorted(area_totals.values(), key=lambda r: r["weight"], reverse=True)[:8]
    monthly_rows = sorted(monthly_totals.values(), key=lambda r: r["month"])[-12:]
    location_rows = sorted(location_inventory.items(), key=lambda r: r[1], reverse=True)[:10]

    recent_purchases = list(reversed(active_purchases[-6:]))
    recent_movements = list(reversed(period_movements[-8:]))

    alerts = []
    for stock in stock_rows:
        location_type = stock.location.location_type if stock.location else ""
        if location_type == "Final Warehouse" and stock.moisture is not None and float(stock.moisture) > 13:
            alerts.append({
                "level": "warning",
                "title": "High moisture in final warehouse",
                "detail": f"{stock.batch.batch_no} · {stock.grade} · {float(stock.moisture):.1f}% moisture",
            })
    today = datetime.utcnow().date()
    for drying in all_drying:
        if drying.drying_status != "Completed" and drying.start_date and (today - drying.start_date).days > 14:
            alerts.append({
                "level": "info",
                "title": "Long-running drying record",
                "detail": f"{drying.batch.batch_no} · {drying.grade} · started {drying.start_date.strftime('%d %b %Y')}",
            })
    alerts = alerts[:8]

    processing_batch_rows = sorted(
        [{"batch": r.batch.batch_no, "outturn": float(r.outturn_percent or 0)} for r in processing_rows],
        key=lambda r: r["batch"],
    )[-10:]

    charts = {
        "monthly": {
            "labels": [r["month"] for r in monthly_rows],
            "weights": [round(r["weight"], 2) for r in monthly_rows],
            "values": [round(r["value"], 2) for r in monthly_rows],
        },
        "areas": {
            "labels": [r["area"] for r in area_rows],
            "weights": [round(r["weight"], 2) for r in area_rows],
        },
        "processes": {
            "labels": list(process_totals.keys()),
            "weights": [round(v, 2) for v in process_totals.values()],
        },
        "grades": {
            "labels": list(grade_inventory.keys()),
            "weights": [round(v, 2) for v in grade_inventory.values()],
        },
        "locations": {
            "labels": [r[0] for r in location_rows],
            "weights": [round(r[1], 2) for r in location_rows],
        },
        "stock_status": {
            "labels": list(status_inventory.keys()),
            "weights": [round(v, 2) for v in status_inventory.values()],
        },
        "outturn": {
            "labels": [r["batch"] for r in processing_batch_rows],
            "values": [round(r["outturn"], 2) for r in processing_batch_rows],
        },
    }

    return render_template(
        "dashboard.html",
        period=period,
        stats=stats,
        recent=recent_purchases,
        recent_movements=recent_movements,
        top_suppliers=top_suppliers,
        alerts=alerts,
        charts=charts,
    )

@app.route("/users", methods=["GET","POST"])
@permission_required("users")
def users():
    if request.method == "POST":
        user = User(
            full_name=request.form["full_name"],
            username=request.form["username"],
            password_hash=generate_password_hash(request.form["password"]),
            role=request.form["role"],
            status=request.form.get("status","Active")
        )
        db.session.add(user); db.session.commit()
        log_action("CREATE", "Users", user.id, f"Created user {user.username} role {user.role}")
        flash("User created.")
        return redirect(url_for("users"))
    return render_template("users.html", rows=User.query.order_by(User.id.desc()).all(), roles=ROLE_PERMISSIONS.keys())

@app.route("/users/<int:id>/toggle", methods=["POST"])
@permission_required("users")
def user_toggle(id):
    user = User.query.get_or_404(id)
    if user.id == session["user_id"]:
        flash("You cannot disable your own active account.")
    else:
        user.status = "Inactive" if user.status == "Active" else "Active"
        db.session.commit()
        log_action("UPDATE", "Users", user.id, f"Status changed to {user.status}")
    return redirect(url_for("users"))

@app.route("/users/<int:id>/reset-password", methods=["POST"])
@permission_required("users")
def reset_password(id):
    user = User.query.get_or_404(id)
    user.password_hash = generate_password_hash(request.form["password"])
    db.session.commit()
    log_action("RESET_PASSWORD", "Users", user.id)
    flash("Password reset.")
    return redirect(url_for("users"))

@app.route("/audit")
@permission_required("users")
def audit():
    return render_template("audit.html", rows=AuditLog.query.order_by(AuditLog.id.desc()).limit(500).all())

@app.route("/suppliers", methods=["GET","POST"])
@permission_required("suppliers")
def suppliers():
    if request.method == "POST":
        s = Supplier(code=request.form["code"], name=request.form["name"], phone=request.form.get("phone"),
                     location=request.form.get("location"), status=request.form.get("status","Active"))
        db.session.add(s); db.session.commit(); log_action("CREATE","Suppliers",s.id)
        return redirect(url_for("suppliers"))
    return render_template("suppliers.html", rows=Supplier.query.order_by(Supplier.id.desc()).all(),
                           next_code=next_code(Supplier,"code","SUP",3))

@app.route("/suppliers/<int:id>/delete", methods=["POST"])
@permission_required("suppliers")
def supplier_delete(id):
    s = Supplier.query.get_or_404(id)
    if Purchase.query.filter_by(supplier_id=id).count():
        s.status = "Inactive"; db.session.commit(); log_action("DEACTIVATE","Suppliers",id)
    else:
        db.session.delete(s); db.session.commit(); log_action("DELETE","Suppliers",id)
    return redirect(url_for("suppliers"))

@app.route("/prices", methods=["GET","POST"])
@permission_required("prices")
def prices():
    if request.method == "POST":
        p = PriceHistory(
            effective_date=datetime.strptime(request.form["effective_date"], "%Y-%m-%d").date(),
            cherry_price=float(request.form["cherry_price"]),
            floater_price=float(request.form["floater_price"]),
            notes=request.form.get("notes")
        )
        db.session.add(p); db.session.commit(); log_action("CREATE","Price History",p.id)
        return redirect(url_for("prices"))
    return render_template("prices.html", rows=PriceHistory.query.order_by(PriceHistory.effective_date.desc()).all())

@app.route("/batches", methods=["GET","POST"])
@permission_required("batches")
def batches():
    if request.method == "POST":
        b = Batch(
            batch_no=request.form["batch_no"],
            batch_date=datetime.strptime(request.form["batch_date"], "%Y-%m-%d").date(),
            process_type=request.form["process_type"],
            status=request.form.get("status","Open"),
            notes=request.form.get("notes")
        )
        db.session.add(b); db.session.commit(); log_action("CREATE","Batches",b.id)
        return redirect(url_for("batches"))
    return render_template("batches.html", rows=Batch.query.order_by(Batch.id.desc()).all(),
                           next_batch=next_code(Batch,"batch_no","STA",3))

@app.route("/purchases", methods=["GET","POST"])
@permission_required("purchases")
def purchases():
    if request.method == "POST":
        d = datetime.strptime(request.form["purchase_date"], "%Y-%m-%d").date()
        price = get_price(d)
        if not price:
            flash("Add price history first."); return redirect(url_for("purchases"))
        gross = float(request.form["gross_weight"]); fl = float(request.form.get("floaters_weight") or 0)
        good = gross - fl; bought = request.form["floaters_bought"]
        cp = price.cherry_price; fp = price.floater_price if bought == "Yes" else 0
        p = Purchase(
            receipt_no=next_code(Purchase,"receipt_no","REC",6),
            purchase_date=d, batch_id=int(request.form["batch_id"]), supplier_id=int(request.form["supplier_id"]),
            gross_weight=gross, floaters_weight=fl, good_weight=good, floaters_bought=bought,
            cherry_price=cp, floater_price=fp, total_amount=good*cp+fl*fp,
            created_by=session["username"]
        )
        db.session.add(p); db.session.commit(); log_action("CREATE","Purchases",p.id,p.receipt_no)
        return redirect(url_for("purchases"))
    return render_template("purchases.html",
        rows=Purchase.query.order_by(Purchase.id.desc()).all(),
        suppliers=Supplier.query.filter_by(status="Active").order_by(Supplier.name).all(),
        batches=Batch.query.filter_by(status="Open").order_by(Batch.batch_date.desc()).all())

@app.route("/purchase-receipt/<int:id>")
@permission_required("purchases")
def purchase_receipt(id):
    return render_template("purchase_receipt.html", row=Purchase.query.get_or_404(id))

@app.route("/purchases/<int:id>/edit", methods=["GET", "POST"])
@permission_required("purchases")
def purchase_edit(id):
    purchase = Purchase.query.get_or_404(id)
    if purchase.status == "Voided":
        flash("A voided purchase cannot be edited.")
        return redirect(url_for("purchases"))

    active_processing = Processing.query.filter_by(batch_id=purchase.batch_id, status="Active").first()
    if active_processing:
        flash("This purchase cannot be edited because its batch has already been processed. Void the processing record first.")
        return redirect(url_for("purchases"))

    if request.method == "POST":
        d = datetime.strptime(request.form["purchase_date"], "%Y-%m-%d").date()
        price = get_price(d)
        if not price:
            flash("Add price history for the selected date first.")
            return redirect(url_for("purchase_edit", id=id))

        gross = float(request.form["gross_weight"])
        floaters = float(request.form.get("floaters_weight") or 0)
        if gross <= 0 or floaters < 0 or floaters > gross:
            flash("Check the weights. Floaters cannot be more than the gross weight.")
            return redirect(url_for("purchase_edit", id=id))

        bought = request.form["floaters_bought"]
        good = gross - floaters
        purchase.purchase_date = d
        purchase.batch_id = int(request.form["batch_id"])
        purchase.supplier_id = int(request.form["supplier_id"])
        purchase.gross_weight = gross
        purchase.floaters_weight = floaters
        purchase.good_weight = good
        purchase.floaters_bought = bought
        purchase.cherry_price = price.cherry_price
        purchase.floater_price = price.floater_price if bought == "Yes" else 0
        purchase.total_amount = good * purchase.cherry_price + floaters * purchase.floater_price
        db.session.commit()
        log_action("UPDATE", "Purchases", purchase.id, purchase.receipt_no)
        flash("Purchase updated successfully.")
        return redirect(url_for("purchases"))

    return render_template(
        "purchase_edit.html",
        row=purchase,
        suppliers=Supplier.query.order_by(Supplier.name).all(),
        batches=Batch.query.order_by(Batch.batch_date.desc()).all(),
    )

@app.route("/purchases/<int:id>/void", methods=["POST"])
@permission_required("purchases")
def purchase_void(id):
    purchase = Purchase.query.get_or_404(id)
    if purchase.status == "Voided":
        flash("This purchase is already voided.")
        return redirect(url_for("purchases"))

    active_processing = Processing.query.filter_by(batch_id=purchase.batch_id, status="Active").first()
    if active_processing:
        flash("This purchase cannot be voided because its batch has already been processed. Void the processing record first.")
        return redirect(url_for("purchases"))

    reason = (request.form.get("void_reason") or "").strip()
    if not reason:
        flash("Enter a reason for voiding the purchase.")
        return redirect(url_for("purchases"))

    purchase.status = "Voided"
    purchase.void_reason = reason
    db.session.commit()
    log_action("VOID", "Purchases", purchase.id, f"{purchase.receipt_no}: {reason}")
    flash("Purchase voided. It will no longer count in totals or processing.")
    return redirect(url_for("purchases"))

@app.route("/purchases/<int:id>/delete", methods=["POST"])
@permission_required("purchases")
def purchase_delete(id):
    if session.get("role") != "Admin":
        abort(403)

    purchase = Purchase.query.get_or_404(id)
    active_processing = Processing.query.filter_by(batch_id=purchase.batch_id, status="Active").first()
    if active_processing:
        flash("This purchase cannot be permanently deleted because its batch has already been processed.")
        return redirect(url_for("purchases"))

    receipt_no = purchase.receipt_no
    db.session.delete(purchase)
    db.session.commit()
    log_action("DELETE", "Purchases", id, receipt_no)
    flash("Purchase permanently deleted.")
    return redirect(url_for("purchases"))

@app.route("/processing", methods=["GET", "POST"])
@permission_required("processing")
def processing():
    if request.method == "POST":
        batch_id = int(request.form["batch_id"])
        if Processing.query.filter_by(batch_id=batch_id).first():
            flash("This batch already has a processing record. Open it and use Edit.")
            return redirect(url_for("processing"))

        input_weight = float(request.form["input_weight"] or 0)
        grade_a = float(request.form.get("grade_a_weight") or 0)
        grade_b = float(request.form.get("grade_b_weight") or 0)
        grade_c = float(request.form.get("grade_c_weight") or 0)
        total_sorted = grade_a + grade_b + grade_c

        if input_weight <= 0:
            flash("Weight entering processing must be greater than zero.")
            return redirect(url_for("processing"))
        if min(grade_a, grade_b, grade_c) < 0:
            flash("Grade weights cannot be negative.")
            return redirect(url_for("processing"))
        if total_sorted > input_weight:
            flash("The total of Grade A, B and C cannot exceed the weight entering processing.")
            return redirect(url_for("processing"))

        loss = input_weight - total_sorted
        outturn = (total_sorted / input_weight * 100) if input_weight else 0
        record = Processing(
            processing_no=next_code(Processing, "processing_no", "PRO", 6),
            processing_date=datetime.strptime(request.form["processing_date"], "%Y-%m-%d").date(),
            batch_id=batch_id,
            input_weight=input_weight,
            grade_a_weight=grade_a,
            grade_b_weight=grade_b,
            grade_c_weight=grade_c,
            total_sorted_weight=total_sorted,
            processing_loss=loss,
            outturn_percent=outturn,
            moisture=float(request.form["moisture"]) if request.form.get("moisture") else None,
            processed_by=request.form.get("processed_by"),
            notes=request.form.get("notes"),
            created_by=session.get("username")
        )
        db.session.add(record)
        batch = db.session.get(Batch, batch_id)
        if batch and batch.status == "Open":
            batch.status = "Processing"
        db.session.commit()
        log_action("CREATE", "Processing", record.id, record.processing_no)
        flash("Processing record saved successfully.")
        return redirect(url_for("processing"))

    batches = Batch.query.order_by(Batch.batch_date.desc(), Batch.id.desc()).all()
    purchase_totals = {}
    for batch in batches:
        total = db.session.query(func.coalesce(func.sum(Purchase.good_weight), 0)).filter(
            Purchase.batch_id == batch.id, Purchase.status == "Active"
        ).scalar()
        purchase_totals[batch.id] = float(total or 0)

    return render_template(
        "processing.html",
        rows=Processing.query.order_by(Processing.id.desc()).all(),
        batches=batches,
        purchase_totals=purchase_totals,
        next_processing=next_code(Processing, "processing_no", "PRO", 6)
    )

@app.route("/processing/<int:id>/edit", methods=["GET", "POST"])
@permission_required("processing")
def processing_edit(id):
    record = Processing.query.get_or_404(id)
    if record.status == "Voided":
        flash("A voided processing record cannot be edited.")
        return redirect(url_for("processing"))
    if Drying.query.filter_by(processing_id=record.id, status="Active").first():
        flash("This processing record cannot be edited because drying has already started. Void the drying record first.")
        return redirect(url_for("processing"))

    if request.method == "POST":
        input_weight = float(request.form["input_weight"] or 0)
        grade_a = float(request.form.get("grade_a_weight") or 0)
        grade_b = float(request.form.get("grade_b_weight") or 0)
        grade_c = float(request.form.get("grade_c_weight") or 0)
        total_sorted = grade_a + grade_b + grade_c

        if input_weight <= 0 or min(grade_a, grade_b, grade_c) < 0 or total_sorted > input_weight:
            flash("Check the weights. Grade totals cannot exceed the input weight.")
            return redirect(url_for("processing_edit", id=id))

        record.processing_date = datetime.strptime(request.form["processing_date"], "%Y-%m-%d").date()
        record.input_weight = input_weight
        record.grade_a_weight = grade_a
        record.grade_b_weight = grade_b
        record.grade_c_weight = grade_c
        record.total_sorted_weight = total_sorted
        record.processing_loss = input_weight - total_sorted
        record.outturn_percent = total_sorted / input_weight * 100
        record.moisture = float(request.form["moisture"]) if request.form.get("moisture") else None
        record.processed_by = request.form.get("processed_by")
        record.notes = request.form.get("notes")
        db.session.commit()
        log_action("UPDATE", "Processing", record.id, record.processing_no)
        flash("Processing record updated.")
        return redirect(url_for("processing"))

    return render_template("processing_edit.html", row=record)

@app.route("/processing/<int:id>/void", methods=["POST"])
@permission_required("processing")
def processing_void(id):
    record = Processing.query.get_or_404(id)
    if Drying.query.filter_by(processing_id=record.id, status="Active").first():
        flash("This processing record cannot be voided because drying has already started. Void the drying record first.")
        return redirect(url_for("processing"))
    reason = (request.form.get("void_reason") or "").strip()
    if not reason:
        flash("Enter a reason before voiding the record.")
        return redirect(url_for("processing"))
    record.status = "Voided"
    record.void_reason = reason
    db.session.commit()
    log_action("VOID", "Processing", record.id, reason)
    flash("Processing record voided. It remains in the audit history.")
    return redirect(url_for("processing"))

@app.route("/processing/<int:id>")
@permission_required("processing")
def processing_detail(id):
    return render_template("processing_detail.html", row=Processing.query.get_or_404(id))


def grade_source_weight(processing_record, grade):
    return {
        "Grade A": processing_record.grade_a_weight,
        "Grade B": processing_record.grade_b_weight,
        "Grade C": processing_record.grade_c_weight,
    }.get(grade, 0)

@app.route("/drying", methods=["GET", "POST"])
@permission_required("drying")
def drying():
    active_processes = Processing.query.filter_by(status="Active").order_by(
        Processing.processing_date.desc(), Processing.id.desc()
    ).all()

    if request.method == "POST":
        processing_id = int(request.form["processing_id"])
        process = Processing.query.get_or_404(processing_id)
        grade = request.form["grade"]
        if grade not in {"Grade A", "Grade B", "Grade C"}:
            flash("Select a valid grade.")
            return redirect(url_for("drying"))

        source_weight = float(grade_source_weight(process, grade) or 0)
        if source_weight <= 0:
            flash(f"{grade} has no weight in this processing record.")
            return redirect(url_for("drying"))

        existing = Drying.query.filter_by(
            processing_id=processing_id, grade=grade, status="Active"
        ).first()
        if existing:
            flash(f"An active drying record already exists for {grade} in this batch. Open it and use Edit.")
            return redirect(url_for("drying"))

        input_weight = float(request.form.get("input_weight") or 0)
        dry_weight_text = request.form.get("dry_weight")
        dry_weight = float(dry_weight_text) if dry_weight_text else None
        if input_weight <= 0 or input_weight > source_weight:
            flash(f"Input weight must be greater than zero and cannot exceed the sorted {grade} weight of {source_weight:,.2f} kg.")
            return redirect(url_for("drying"))
        if dry_weight is not None and (dry_weight < 0 or dry_weight > input_weight):
            flash("Dry weight cannot be negative or greater than the input weight.")
            return redirect(url_for("drying"))

        start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
        end_text = request.form.get("end_date")
        end_date = datetime.strptime(end_text, "%Y-%m-%d").date() if end_text else None
        if end_date and end_date < start_date:
            flash("End date cannot be earlier than the start date.")
            return redirect(url_for("drying"))

        drying_status = "Completed" if dry_weight is not None and end_date else "Drying"
        loss = input_weight - dry_weight if dry_weight is not None else 0
        outturn = dry_weight / input_weight * 100 if dry_weight is not None and input_weight else 0
        row = Drying(
            drying_no=next_code(Drying, "drying_no", "DRY", 6),
            processing_id=process.id,
            batch_id=process.batch_id,
            grade=grade,
            start_date=start_date,
            end_date=end_date,
            input_weight=input_weight,
            dry_weight=dry_weight,
            drying_loss=loss,
            outturn_percent=outturn,
            moisture=float(request.form["moisture"]) if request.form.get("moisture") else None,
            drying_location=request.form.get("drying_location"),
            dried_by=request.form.get("dried_by"),
            drying_status=drying_status,
            notes=request.form.get("notes"),
            created_by=session.get("username")
        )
        db.session.add(row)
        process.batch.status = "Drying"
        db.session.commit()
        log_action("CREATE", "Drying", row.id, row.drying_no)
        flash("Drying record saved successfully.")
        return redirect(url_for("drying"))

    grade_weights = {
        p.id: {
            "Grade A": float(p.grade_a_weight or 0),
            "Grade B": float(p.grade_b_weight or 0),
            "Grade C": float(p.grade_c_weight or 0),
        } for p in active_processes
    }
    return render_template(
        "drying.html",
        rows=Drying.query.order_by(Drying.id.desc()).all(),
        processes=active_processes,
        grade_weights=grade_weights,
        next_drying=next_code(Drying, "drying_no", "DRY", 6)
    )

@app.route("/drying/<int:id>/edit", methods=["GET", "POST"])
@permission_required("drying")
def drying_edit(id):
    row = Drying.query.get_or_404(id)
    if row.status == "Voided":
        flash("A voided drying record cannot be edited.")
        return redirect(url_for("drying"))

    source_weight = float(grade_source_weight(row.processing, row.grade) or 0)
    if request.method == "POST":
        input_weight = float(request.form.get("input_weight") or 0)
        dry_text = request.form.get("dry_weight")
        dry_weight = float(dry_text) if dry_text else None
        if input_weight <= 0 or input_weight > source_weight:
            flash(f"Input weight cannot exceed the sorted {row.grade} weight of {source_weight:,.2f} kg.")
            return redirect(url_for("drying_edit", id=id))
        if dry_weight is not None and (dry_weight < 0 or dry_weight > input_weight):
            flash("Dry weight cannot be negative or greater than input weight.")
            return redirect(url_for("drying_edit", id=id))

        start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
        end_text = request.form.get("end_date")
        end_date = datetime.strptime(end_text, "%Y-%m-%d").date() if end_text else None
        if end_date and end_date < start_date:
            flash("End date cannot be earlier than start date.")
            return redirect(url_for("drying_edit", id=id))

        row.start_date = start_date
        row.end_date = end_date
        row.input_weight = input_weight
        row.dry_weight = dry_weight
        row.drying_loss = input_weight - dry_weight if dry_weight is not None else 0
        row.outturn_percent = dry_weight / input_weight * 100 if dry_weight is not None else 0
        row.moisture = float(request.form["moisture"]) if request.form.get("moisture") else None
        row.drying_location = request.form.get("drying_location")
        row.dried_by = request.form.get("dried_by")
        row.drying_status = "Completed" if dry_weight is not None and end_date else "Drying"
        row.notes = request.form.get("notes")
        db.session.commit()
        log_action("UPDATE", "Drying", row.id, row.drying_no)
        flash("Drying record updated successfully.")
        return redirect(url_for("drying"))

    return render_template("drying_edit.html", row=row, source_weight=source_weight)

@app.route("/drying/<int:id>/void", methods=["POST"])
@permission_required("drying")
def drying_void(id):
    row = Drying.query.get_or_404(id)
    reason = (request.form.get("void_reason") or "").strip()
    if not reason:
        flash("Enter a reason before voiding the drying record.")
        return redirect(url_for("drying"))
    row.status = "Voided"
    row.void_reason = reason
    db.session.commit()
    log_action("VOID", "Drying", row.id, f"{row.drying_no}: {reason}")
    flash("Drying record voided. It remains in the audit history.")
    return redirect(url_for("drying"))

@app.route("/drying/<int:id>")
@permission_required("drying")
def drying_detail(id):
    return render_template("drying_detail.html", row=Drying.query.get_or_404(id))


def stock_status_for_location(location_type):
    return {
        "Drying Area": "Drying",
        "Temporary Storage": "Temporary Storage",
        "Final Warehouse": "Final Storage",
    }.get(location_type, "In Transit")


def ensure_initial_stock():
    """Create a starting inventory balance for existing active drying records.
    This adds records only and never changes purchase, processing or drying data.
    """
    changed = False
    active_drying = Drying.query.filter_by(status="Active").all()
    for row in active_drying:
        existing = CoffeeStock.query.filter_by(drying_id=row.id).first()
        movement = CoffeeMovement.query.filter_by(drying_id=row.id, status="Active").first()
        if existing or movement:
            continue
        location_name = (row.drying_location or "Unspecified Drying Area").strip()
        location = Location.query.filter(func.lower(Location.name) == location_name.lower()).first()
        if not location:
            location = Location(name=location_name, location_type="Drying Area", status="Active")
            db.session.add(location)
            db.session.flush()
        starting_weight = float(row.dry_weight if row.drying_status == "Completed" and row.dry_weight is not None else row.input_weight or 0)
        if starting_weight <= 0:
            continue
        stock = CoffeeStock(
            drying_id=row.id,
            batch_id=row.batch_id,
            grade=row.grade,
            location_id=location.id,
            weight=starting_weight,
            moisture=row.moisture,
            stock_status="Drying" if row.drying_status != "Completed" else "Fully Dry",
        )
        db.session.add(stock)
        changed = True
    if changed:
        db.session.commit()


@app.route("/locations", methods=["GET", "POST"])
@permission_required("locations")
def locations():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        location_type = request.form.get("location_type")
        if not name or location_type not in {"Drying Area", "Temporary Storage", "Final Warehouse"}:
            flash("Enter a location name and select a valid location type.")
            return redirect(url_for("locations"))
        if Location.query.filter(func.lower(Location.name) == name.lower()).first():
            flash("A location with this name already exists.")
            return redirect(url_for("locations"))
        row = Location(name=name, location_type=location_type, notes=request.form.get("notes"))
        db.session.add(row)
        db.session.commit()
        log_action("CREATE", "Locations", row.id, f"{row.name} - {row.location_type}")
        flash("Location added successfully.")
        return redirect(url_for("locations"))
    return render_template("locations.html", rows=Location.query.order_by(Location.location_type, Location.name).all())


@app.route("/locations/<int:id>/toggle", methods=["POST"])
@permission_required("locations")
def location_toggle(id):
    row = Location.query.get_or_404(id)
    row.status = "Inactive" if row.status == "Active" else "Active"
    db.session.commit()
    log_action("UPDATE", "Locations", row.id, f"Status changed to {row.status}")
    flash("Location status updated.")
    return redirect(url_for("locations"))


@app.route("/inventory", methods=["GET", "POST"])
@permission_required("inventory")
def inventory():
    ensure_initial_stock()
    if request.method == "POST":
        source_id = int(request.form["source_stock_id"])
        destination_id = int(request.form["to_location_id"])
        source = CoffeeStock.query.get_or_404(source_id)
        destination = Location.query.get_or_404(destination_id)
        weight = float(request.form.get("weight") or 0)
        if source.weight <= 0:
            flash("The selected source has no available coffee.")
            return redirect(url_for("inventory"))
        if source.location_id == destination.id:
            flash("Choose a different destination.")
            return redirect(url_for("inventory"))
        if weight <= 0 or weight > source.weight + 0.0001:
            flash(f"Movement weight must be greater than zero and cannot exceed {source.weight:,.2f} kg.")
            return redirect(url_for("inventory"))

        moisture = float(request.form["moisture"]) if request.form.get("moisture") else source.moisture
        destination_stock = CoffeeStock.query.filter_by(
            drying_id=source.drying_id, location_id=destination.id
        ).first()
        old_destination_weight = float(destination_stock.weight or 0) if destination_stock else 0
        if not destination_stock:
            destination_stock = CoffeeStock(
                drying_id=source.drying_id,
                batch_id=source.batch_id,
                grade=source.grade,
                location_id=destination.id,
                weight=0,
                moisture=moisture,
            )
            db.session.add(destination_stock)
        new_total = old_destination_weight + weight
        if moisture is not None:
            old_m = float(destination_stock.moisture or moisture)
            destination_stock.moisture = ((old_destination_weight * old_m) + (weight * moisture)) / new_total if new_total else moisture
        destination_stock.weight = new_total
        destination_stock.stock_status = stock_status_for_location(destination.location_type)

        source.weight = max(0, float(source.weight or 0) - weight)
        source.stock_status = stock_status_for_location(source.location.location_type)

        movement_type = {
            "Drying Area": "Return to Drying",
            "Temporary Storage": "Temporary Storage",
            "Final Warehouse": "Final Storage",
        }.get(destination.location_type, "Transfer")
        movement = CoffeeMovement(
            movement_no=next_code(CoffeeMovement, "movement_no", "MOV", 6),
            drying_id=source.drying_id,
            batch_id=source.batch_id,
            grade=source.grade,
            from_location_id=source.location_id,
            to_location_id=destination.id,
            movement_date=datetime.strptime(request.form["movement_date"], "%Y-%m-%d").date(),
            weight=weight,
            moisture=moisture,
            movement_type=movement_type,
            reason=request.form.get("reason"),
            moved_by=request.form.get("moved_by"),
            created_by=session.get("username"),
        )
        db.session.add(movement)
        batch = db.session.get(Batch, source.batch_id)
        if batch:
            batch.status = movement_type
        db.session.commit()
        log_action("CREATE", "Inventory Movement", movement.id, movement.movement_no)
        flash(f"Movement saved. {weight:,.2f} kg moved to {destination.name}.")
        return redirect(url_for("inventory"))

    stocks = CoffeeStock.query.filter(CoffeeStock.weight > 0.0001).order_by(CoffeeStock.updated_at.desc()).all()
    locations_list = Location.query.filter_by(status="Active").order_by(Location.location_type, Location.name).all()
    movements = CoffeeMovement.query.order_by(CoffeeMovement.id.desc()).limit(200).all()
    grade_totals = {"Grade A": 0.0, "Grade B": 0.0, "Grade C": 0.0}
    location_totals = {}
    for stock in stocks:
        grade_totals[stock.grade] = grade_totals.get(stock.grade, 0) + float(stock.weight or 0)
        location_totals.setdefault(stock.location.name, 0.0)
        location_totals[stock.location.name] += float(stock.weight or 0)
    return render_template(
        "inventory.html",
        stocks=stocks,
        locations=locations_list,
        movements=movements,
        grade_totals=grade_totals,
        total_stock=sum(grade_totals.values()),
        location_totals=location_totals,
        next_movement=next_code(CoffeeMovement, "movement_no", "MOV", 6),
    )


@app.route("/inventory/movement/<int:id>/print")
@permission_required("inventory")
def inventory_movement_print(id):
    movement = CoffeeMovement.query.get_or_404(id)
    return render_template("moving_form.html", movement=movement, dispatch=None)


@app.route("/inventory/movement/<int:id>/void", methods=["POST"])
@permission_required("inventory")
def inventory_movement_void(id):
    movement = CoffeeMovement.query.get_or_404(id)
    if movement.status == "Voided":
        flash("This movement is already voided.")
        return redirect(url_for("inventory"))
    reason = (request.form.get("void_reason") or "").strip()
    if not reason:
        flash("Enter a reason before voiding the movement.")
        return redirect(url_for("inventory"))
    destination_stock = CoffeeStock.query.filter_by(
        drying_id=movement.drying_id, location_id=movement.to_location_id
    ).first()
    source_stock = CoffeeStock.query.filter_by(
        drying_id=movement.drying_id, location_id=movement.from_location_id
    ).first()
    if not destination_stock or destination_stock.weight + 0.0001 < movement.weight:
        flash("This movement cannot be reversed because some of that coffee has already moved onward.")
        return redirect(url_for("inventory"))
    if not source_stock:
        source_stock = CoffeeStock(
            drying_id=movement.drying_id, batch_id=movement.batch_id, grade=movement.grade,
            location_id=movement.from_location_id, weight=0,
            stock_status=stock_status_for_location(movement.from_location.location_type)
        )
        db.session.add(source_stock)
    destination_stock.weight = max(0, destination_stock.weight - movement.weight)
    source_stock.weight += movement.weight
    source_stock.moisture = movement.moisture
    movement.status = "Voided"
    movement.void_reason = reason
    db.session.commit()
    log_action("VOID", "Inventory Movement", movement.id, f"{movement.movement_no}: {reason}")
    flash("Movement reversed and marked as voided.")
    return redirect(url_for("inventory"))


@app.route("/inventory/batch/<int:batch_id>")
@permission_required("inventory")
def inventory_batch_history(batch_id):
    ensure_initial_stock()
    batch = Batch.query.get_or_404(batch_id)
    purchases = Purchase.query.filter_by(batch_id=batch_id).order_by(Purchase.purchase_date).all()
    process = Processing.query.filter_by(batch_id=batch_id).first()
    drying_rows = Drying.query.filter_by(batch_id=batch_id).order_by(Drying.start_date).all()
    stocks = CoffeeStock.query.filter_by(batch_id=batch_id).filter(CoffeeStock.weight > 0.0001).all()
    movements = CoffeeMovement.query.filter_by(batch_id=batch_id).order_by(CoffeeMovement.movement_date, CoffeeMovement.id).all()
    dispatches = Dispatch.query.filter_by(batch_id=batch_id).order_by(Dispatch.dispatch_date, Dispatch.id).all()
    return render_template("batch_history.html", batch=batch, purchases=purchases, process=process,
                           drying_rows=drying_rows, stocks=stocks, movements=movements, dispatches=dispatches)


def update_sale_status(sale):
    active_dispatched = db.session.query(func.coalesce(func.sum(Dispatch.weight), 0)).filter(
        Dispatch.sale_id == sale.id, Dispatch.status == "Active"
    ).scalar() or 0
    if sale.status == "Voided":
        return
    if sale.contracted_weight > 0 and active_dispatched + 0.0001 >= sale.contracted_weight:
        sale.status = "Completed"
    else:
        sale.status = "Open"


@app.route("/sales", methods=["GET", "POST"])
@permission_required("sales")
def sales():
    if request.method == "POST":
        contracted_weight = float(request.form.get("contracted_weight") or 0)
        price_per_kg = float(request.form.get("price_per_kg") or 0)
        if contracted_weight < 0 or price_per_kg < 0:
            flash("Weight and price cannot be negative.")
            return redirect(url_for("sales"))
        row = Sale(
            sale_no=next_code(Sale, "sale_no", "SAL", 6),
            sale_date=datetime.strptime(request.form["sale_date"], "%Y-%m-%d").date(),
            buyer_name=(request.form.get("buyer_name") or "").strip(),
            buyer_phone=request.form.get("buyer_phone"),
            destination=(request.form.get("destination") or "").strip(),
            contract_ref=request.form.get("contract_ref"),
            contracted_weight=contracted_weight,
            price_per_kg=price_per_kg,
            total_value=contracted_weight * price_per_kg,
            notes=request.form.get("notes"),
            created_by=session.get("username"),
        )
        if not row.buyer_name or not row.destination:
            flash("Enter the buyer and destination.")
            return redirect(url_for("sales"))
        db.session.add(row)
        db.session.commit()
        log_action("CREATE", "Sales", row.id, row.sale_no)
        flash("Sale created successfully. You can now record dispatches against it.")
        return redirect(url_for("sale_detail", id=row.id))
    rows = Sale.query.order_by(Sale.id.desc()).all()
    dispatched = dict(db.session.query(Dispatch.sale_id, func.coalesce(func.sum(Dispatch.weight), 0)).filter(
        Dispatch.status == "Active"
    ).group_by(Dispatch.sale_id).all())
    return render_template("sales.html", rows=rows, dispatched=dispatched, next_sale=next_code(Sale, "sale_no", "SAL", 6))


@app.route("/sales/<int:id>")
@permission_required("sales")
def sale_detail(id):
    ensure_initial_stock()
    sale = Sale.query.get_or_404(id)
    stocks = CoffeeStock.query.filter(CoffeeStock.weight > 0.0001).order_by(CoffeeStock.updated_at.desc()).all()
    dispatches = Dispatch.query.filter_by(sale_id=id).order_by(Dispatch.id.desc()).all()
    dispatched_weight = sum(float(d.weight or 0) for d in dispatches if d.status == "Active")
    remaining_weight = max(0, float(sale.contracted_weight or 0) - dispatched_weight)
    return render_template("sale_detail.html", sale=sale, stocks=stocks, dispatches=dispatches,
                           dispatched_weight=dispatched_weight, remaining_weight=remaining_weight,
                           next_dispatch=next_code(Dispatch, "dispatch_no", "DSP", 6))


@app.route("/sales/<int:id>/dispatch", methods=["POST"])
@permission_required("dispatch")
def sale_dispatch(id):
    sale = Sale.query.get_or_404(id)
    if sale.status == "Voided":
        flash("A voided sale cannot receive a dispatch.")
        return redirect(url_for("sales"))
    stock = CoffeeStock.query.get_or_404(int(request.form["stock_id"]))
    weight = float(request.form.get("weight") or 0)
    if weight <= 0 or weight > float(stock.weight or 0) + 0.0001:
        flash(f"Dispatch weight must be greater than zero and cannot exceed {stock.weight:,.2f} kg.")
        return redirect(url_for("sale_detail", id=id))
    dispatch = Dispatch(
        dispatch_no=next_code(Dispatch, "dispatch_no", "DSP", 6),
        sale_id=sale.id, stock_id=stock.id, batch_id=stock.batch_id, grade=stock.grade,
        from_location_id=stock.location_id,
        dispatch_date=datetime.strptime(request.form["dispatch_date"], "%Y-%m-%d").date(),
        weight=weight,
        number_of_bags=int(request.form["number_of_bags"]) if request.form.get("number_of_bags") else None,
        bag_size=float(request.form["bag_size"]) if request.form.get("bag_size") else None,
        moisture=float(request.form["moisture"]) if request.form.get("moisture") else stock.moisture,
        vehicle_no=request.form.get("vehicle_no"), driver_name=request.form.get("driver_name"),
        driver_phone=request.form.get("driver_phone"),
        destination=(request.form.get("destination") or sale.destination).strip(),
        reason=request.form.get("reason"), dispatched_by=request.form.get("dispatched_by"),
        created_by=session.get("username"),
    )
    stock.weight = max(0, float(stock.weight or 0) - weight)
    db.session.add(dispatch)
    update_sale_status(sale)
    if stock.batch:
        stock.batch.status = "Dispatched"
    db.session.commit()
    log_action("CREATE", "Dispatch", dispatch.id, dispatch.dispatch_no)
    flash("Dispatch saved. The moving form is ready to print.")
    return redirect(url_for("dispatch_print", id=dispatch.id))


@app.route("/dispatch/<int:id>/print")
@permission_required("dispatch")
def dispatch_print(id):
    dispatch = Dispatch.query.get_or_404(id)
    return render_template("moving_form.html", movement=None, dispatch=dispatch)


@app.route("/dispatch/<int:id>/void", methods=["POST"])
@permission_required("dispatch")
def dispatch_void(id):
    dispatch = Dispatch.query.get_or_404(id)
    if dispatch.status == "Voided":
        flash("This dispatch is already voided.")
        return redirect(url_for("sale_detail", id=dispatch.sale_id))
    reason = (request.form.get("void_reason") or "").strip()
    if not reason:
        flash("Enter a reason before voiding the dispatch.")
        return redirect(url_for("sale_detail", id=dispatch.sale_id))
    dispatch.stock.weight = float(dispatch.stock.weight or 0) + float(dispatch.weight or 0)
    dispatch.status = "Voided"
    dispatch.void_reason = reason
    update_sale_status(dispatch.sale)
    db.session.commit()
    log_action("VOID", "Dispatch", dispatch.id, f"{dispatch.dispatch_no}: {reason}")
    flash("Dispatch reversed and marked as voided. The stock has been returned to its source location.")
    return redirect(url_for("sale_detail", id=dispatch.sale_id))


@app.route("/sales/<int:id>/void", methods=["POST"])
@permission_required("sales")
def sale_void(id):
    sale = Sale.query.get_or_404(id)
    active_dispatch = Dispatch.query.filter_by(sale_id=id, status="Active").first()
    if active_dispatch:
        flash("Void the active dispatches before voiding this sale.")
        return redirect(url_for("sale_detail", id=id))
    reason = (request.form.get("void_reason") or "").strip()
    if not reason:
        flash("Enter a reason before voiding the sale.")
        return redirect(url_for("sale_detail", id=id))
    sale.status = "Voided"
    sale.void_reason = reason
    db.session.commit()
    log_action("VOID", "Sales", sale.id, f"{sale.sale_no}: {reason}")
    flash("Sale marked as voided.")
    return redirect(url_for("sales"))


@app.route("/casuals", methods=["GET","POST"])
@permission_required("casuals")
def casuals():
    if request.method == "POST":
        c = Casual(code=request.form["code"], name=request.form["name"], sex=request.form["sex"],
                   phone=request.form.get("phone"), status=request.form.get("status","Active"))
        db.session.add(c); db.session.commit(); log_action("CREATE","Casuals",c.id)
        return redirect(url_for("casuals"))
    return render_template("casuals.html", rows=Casual.query.order_by(Casual.id.desc()).all(),
                           next_code=next_code(Casual,"code","CAS",3))

@app.route("/casual-rates", methods=["GET","POST"])
@permission_required("rates")
def casual_rates():
    if request.method == "POST":
        r = CasualRate(
            casual_id=int(request.form["casual_id"]),
            effective_date=datetime.strptime(request.form["effective_date"], "%Y-%m-%d").date(),
            daily_rate=float(request.form["daily_rate"]),
            notes=request.form.get("notes")
        )
        db.session.add(r); db.session.commit(); log_action("CREATE","Casual Rates",r.id)
        return redirect(url_for("casual_rates"))
    return render_template("casual_rates.html", rows=CasualRate.query.order_by(CasualRate.effective_date.desc()).all(),
                           casuals=Casual.query.filter_by(status="Active").order_by(Casual.name).all())

@app.route("/attendance", methods=["GET","POST"])
@permission_required("attendance")
def attendance():
    if request.method == "POST":
        d = datetime.strptime(request.form["work_date"], "%Y-%m-%d").date()
        cid = int(request.form["casual_id"])
        rr = get_rate(cid, d)
        if not rr:
            flash("Add a rate for this worker before recording attendance.")
            return redirect(url_for("attendance"))
        work_type = request.form["work_type"]
        amount = rr.daily_rate if work_type == "Full Day" else rr.daily_rate / 2
        a = Attendance(
            work_date=d,
            casual_id=cid,
            work_done=request.form.get("work_done"),
            work_type=work_type,
            rate=rr.daily_rate,
            amount=amount,
        )
        db.session.add(a)
        db.session.commit()
        log_action("CREATE", "Attendance", a.id,
                   f"{a.casual.name}; {a.work_date}; {a.work_type}; UGX {a.amount:,.0f}")
        flash("Attendance saved.")
        return redirect(url_for("attendance"))

    query = Attendance.query
    worker_id = request.args.get("worker_id", type=int)
    status = request.args.get("status", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    if worker_id:
        query = query.filter(Attendance.casual_id == worker_id)
    if status:
        query = query.filter(Attendance.status == status)
    if date_from:
        query = query.filter(Attendance.work_date >= datetime.strptime(date_from, "%Y-%m-%d").date())
    if date_to:
        query = query.filter(Attendance.work_date <= datetime.strptime(date_to, "%Y-%m-%d").date())
    rows = query.order_by(Attendance.work_date.desc(), Attendance.id.desc()).all()

    # Seven-day cards are calculated from each worker's own attendance cycle.
    # The first non-voided attendance date becomes that worker's cycle start,
    # so workers are not forced into a Monday-to-Sunday calendar week.
    weekly = {}
    card_rows = Attendance.query.filter(Attendance.status != "Voided").order_by(
        Attendance.work_date.asc(), Attendance.id.asc()
    ).all()
    cycle_starts = {}
    for row in card_rows:
        cycle_starts.setdefault(row.casual_id, row.work_date)

    for row in card_rows:
        anchor = cycle_starts[row.casual_id]
        cycle_number = (row.work_date - anchor).days // 7
        week_start = anchor + timedelta(days=cycle_number * 7)
        day_index = (row.work_date - week_start).days
        key = (row.casual_id, week_start)
        item = weekly.setdefault(key, {
            "casual": row.casual,
            "start": week_start,
            "end": week_start + timedelta(days=6),
            "days": 0.0,
            "amount": 0.0,
            "unpaid_amount": 0.0,
            "paid": 0,
            "unpaid": 0,
            "day_entries": {i: [] for i in range(7)},
            "day_labels": [
                (week_start + timedelta(days=i)).strftime("%a") for i in range(7)
            ],
            "day_dates": [
                (week_start + timedelta(days=i)).strftime("%d %b") for i in range(7)
            ],
        })
        day_value = 1 if row.work_type == "Full Day" else 0.5
        item["days"] += day_value
        item["amount"] += float(row.amount or 0)
        item["day_entries"][day_index].append(row)
        if row.status == "Paid":
            item["paid"] += 1
        else:
            item["unpaid"] += 1
            item["unpaid_amount"] += float(row.amount or 0)

    weekly_cards = sorted(
        weekly.values(), key=lambda x: (x["start"], x["casual"].name), reverse=True
    )[:40]

    return render_template(
        "attendance.html",
        rows=rows,
        weekly_cards=weekly_cards,
        casuals=Casual.query.filter_by(status="Active").order_by(Casual.name).all(),
        all_casuals=Casual.query.order_by(Casual.name).all(),
        filters={"worker_id": worker_id, "status": status, "date_from": date_from, "date_to": date_to},
    )


def recalculate_payment(payment_ref):
    if not payment_ref:
        return
    payment = Payment.query.filter_by(payment_ref=payment_ref).first()
    if not payment or payment.status == "Voided":
        return
    paid_entries = Attendance.query.filter_by(payment_ref=payment_ref, status="Paid").all()
    payment.gross_pay = sum(x.amount for x in paid_entries)
    payment.net_paid = max(0, payment.gross_pay - (payment.deduction or 0))


@app.route("/attendance/<int:id>/edit", methods=["GET", "POST"])
@permission_required("attendance")
def attendance_edit(id):
    row = Attendance.query.get_or_404(id)
    if row.status == "Voided":
        flash("A voided attendance entry cannot be edited.")
        return redirect(url_for("attendance"))
    if request.method == "POST":
        old = f"{row.work_date}; {row.casual.name}; {row.work_type}; UGX {row.amount:,.0f}; {row.work_done or ''}"
        old_payment_ref = row.payment_ref
        work_date = datetime.strptime(request.form["work_date"], "%Y-%m-%d").date()
        casual_id = int(request.form["casual_id"])
        rr = get_rate(casual_id, work_date)
        if not rr:
            flash("Add a rate for this worker before saving the correction.")
            return redirect(url_for("attendance_edit", id=id))
        row.work_date = work_date
        row.casual_id = casual_id
        row.work_done = request.form.get("work_done")
        row.work_type = request.form["work_type"]
        row.rate = rr.daily_rate
        row.amount = rr.daily_rate if row.work_type == "Full Day" else rr.daily_rate / 2
        recalculate_payment(old_payment_ref)
        db.session.commit()
        new = f"{row.work_date}; {row.casual.name}; {row.work_type}; UGX {row.amount:,.0f}; {row.work_done or ''}"
        log_action("EDIT", "Attendance", row.id, f"Before: {old} | After: {new}")
        flash("Attendance corrected. Any linked payment total was recalculated.")
        return redirect(url_for("attendance"))
    return render_template("attendance_edit.html", row=row,
                           casuals=Casual.query.order_by(Casual.name).all())


@app.route("/attendance/<int:id>/void", methods=["POST"])
@permission_required("attendance")
def attendance_void(id):
    row = Attendance.query.get_or_404(id)
    if row.status == "Voided":
        flash("This attendance entry is already voided.")
        return redirect(url_for("attendance"))
    reason = request.form.get("reason", "").strip()
    if not reason:
        flash("Enter a reason for voiding the attendance entry.")
        return redirect(url_for("attendance"))
    payment_ref = row.payment_ref
    row.status = "Voided"
    row.work_done = f"{row.work_done or ''} [VOID REASON: {reason}]".strip()
    recalculate_payment(payment_ref)
    db.session.commit()
    log_action("VOID", "Attendance", row.id, f"{row.casual.name}; {row.work_date}; {reason}")
    flash("Attendance entry voided and excluded from payroll totals.")
    return redirect(url_for("attendance"))


@app.route("/attendance/<int:id>/delete", methods=["POST"])
@permission_required("attendance")
def attendance_delete(id):
    if session.get("role") != "Admin":
        abort(403)
    row = Attendance.query.get_or_404(id)
    if row.status == "Paid" or row.payment_ref:
        flash("Paid attendance cannot be permanently deleted. Void it instead.")
        return redirect(url_for("attendance"))
    details = f"{row.casual.name}; {row.work_date}; {row.work_type}; UGX {row.amount:,.0f}"
    db.session.delete(row)
    db.session.commit()
    log_action("DELETE", "Attendance", id, details)
    flash("Unpaid attendance entry permanently deleted.")
    return redirect(url_for("attendance"))


@app.route("/casual/<int:id>")
@permission_required("casuals")
def casual_profile(id):
    casual = Casual.query.get_or_404(id)
    attendance_rows = Attendance.query.filter_by(casual_id=id).order_by(Attendance.work_date.desc()).all()
    payment_rows = Payment.query.filter_by(casual_id=id).order_by(Payment.payment_date.desc()).all()
    active_attendance = [x for x in attendance_rows if x.status != "Voided"]
    total_days = sum(1 if x.work_type == "Full Day" else 0.5 for x in active_attendance)
    total_earned = sum(x.amount for x in active_attendance)
    total_paid = sum(x.net_paid for x in payment_rows if x.status == "Paid")
    unpaid = sum(x.amount for x in active_attendance if x.status == "Unpaid")
    return render_template("casual_profile.html", casual=casual, attendance_rows=attendance_rows,
                           payment_rows=payment_rows, total_days=total_days,
                           total_earned=total_earned, total_paid=total_paid, unpaid=unpaid)


@app.route("/casual/<int:id>/status", methods=["POST"])
@permission_required("casuals")
def casual_status(id):
    casual = Casual.query.get_or_404(id)
    old = casual.status
    casual.status = "Inactive" if casual.status == "Active" else "Active"
    db.session.commit()
    log_action("EDIT", "Casuals", casual.id, f"Status: {old} → {casual.status}")
    flash(f"{casual.name} is now {casual.status}.")
    return redirect(url_for("casual_profile", id=id))


@app.route("/payments/calculate")
@permission_required("payments")
def payment_calculate():
    """Return an automatic preview of unpaid attendance for a selected period."""
    cid = request.args.get("casual_id", type=int)
    start_text = request.args.get("period_start", "")
    end_text = request.args.get("period_end", "")
    if not cid or not start_text or not end_text:
        return {"ok": False, "message": "Select a worker and both period dates."}, 400
    try:
        start = datetime.strptime(start_text, "%Y-%m-%d").date()
        end = datetime.strptime(end_text, "%Y-%m-%d").date()
    except ValueError:
        return {"ok": False, "message": "Enter valid dates."}, 400
    if end < start:
        return {"ok": False, "message": "The period end cannot be before the start."}, 400

    entries = Attendance.query.filter(
        Attendance.casual_id == cid,
        Attendance.work_date >= start,
        Attendance.work_date <= end,
        Attendance.status == "Unpaid",
    ).order_by(Attendance.work_date).all()
    gross = sum(float(x.amount or 0) for x in entries)
    full_days = sum(1 for x in entries if x.work_type == "Full Day")
    half_days = sum(1 for x in entries if x.work_type == "Half Day")
    return {
        "ok": True,
        "entry_count": len(entries),
        "full_days": full_days,
        "half_days": half_days,
        "days_equivalent": full_days + (half_days * 0.5),
        "gross_pay": gross,
        "entries": [
            {
                "date": x.work_date.isoformat(),
                "work_type": x.work_type,
                "work_done": x.work_done or "-",
                "amount": float(x.amount or 0),
            } for x in entries
        ],
    }


@app.route("/payments", methods=["GET","POST"])
@permission_required("payments")
def payments():
    if request.method == "POST":
        cid = int(request.form["casual_id"])
        start = datetime.strptime(request.form["period_start"], "%Y-%m-%d").date()
        end = datetime.strptime(request.form["period_end"], "%Y-%m-%d").date()
        if end < start:
            flash("The period end cannot be before the period start.")
            return redirect(url_for("payments"))
        entries = Attendance.query.filter(
            Attendance.casual_id == cid,
            Attendance.work_date >= start,
            Attendance.work_date <= end,
            Attendance.status == "Unpaid",
        ).all()
        if not entries:
            flash("There is no unpaid attendance for this worker in the selected period.")
            return redirect(url_for("payments"))
        gross = sum(x.amount for x in entries)
        deduction = float(request.form.get("deduction") or 0)
        p = Payment(
            payment_ref=next_code(Payment, "payment_ref", "PAY", 6),
            casual_id=cid,
            period_start=start,
            period_end=end,
            gross_pay=gross,
            deduction=deduction,
            net_paid=max(0, gross-deduction),
            payment_date=datetime.strptime(request.form["payment_date"], "%Y-%m-%d").date(),
            method=request.form["method"],
        )
        db.session.add(p)
        for x in entries:
            x.status = "Paid"
            x.payment_ref = p.payment_ref
        db.session.commit()
        log_action("CREATE", "Payments", p.id,
                   f"{p.payment_ref}; {p.casual.name}; UGX {p.net_paid:,.0f}")
        flash("Payment saved. You can now print the receipt.")
        return redirect(url_for("payments"))
    return render_template(
        "payments.html",
        rows=Payment.query.order_by(Payment.id.desc()).all(),
        casuals=Casual.query.filter_by(status="Active").order_by(Casual.name).all(),
        prefill={
            "casual_id": request.args.get("casual_id", type=int),
            "period_start": request.args.get("period_start", ""),
            "period_end": request.args.get("period_end", ""),
        },
    )


@app.route("/payment/<int:id>/edit", methods=["GET", "POST"])
@permission_required("payments")
def payment_edit(id):
    row = Payment.query.get_or_404(id)
    if row.status == "Voided":
        flash("A voided payment cannot be edited.")
        return redirect(url_for("payments"))
    if request.method == "POST":
        old = f"Date {row.payment_date}; Method {row.method}; Deduction {row.deduction}; Net {row.net_paid}"
        row.payment_date = datetime.strptime(request.form["payment_date"], "%Y-%m-%d").date()
        row.method = request.form["method"]
        row.deduction = float(request.form.get("deduction") or 0)
        recalculate_payment(row.payment_ref)
        db.session.commit()
        new = f"Date {row.payment_date}; Method {row.method}; Deduction {row.deduction}; Net {row.net_paid}"
        log_action("EDIT", "Payments", row.id, f"{row.payment_ref} | Before: {old} | After: {new}")
        flash("Payment details updated.")
        return redirect(url_for("payments"))
    return render_template("payment_edit.html", row=row)


@app.route("/payment/<int:id>/void", methods=["POST"])
@permission_required("payments")
def payment_void(id):
    row = Payment.query.get_or_404(id)
    if row.status == "Voided":
        flash("This payment is already voided.")
        return redirect(url_for("payments"))
    reason = request.form.get("reason", "").strip()
    if not reason:
        flash("Enter a reason for voiding the payment.")
        return redirect(url_for("payments"))
    linked = Attendance.query.filter_by(payment_ref=row.payment_ref, status="Paid").all()
    for entry in linked:
        entry.status = "Unpaid"
        entry.payment_ref = None
    row.status = "Voided"
    row.void_reason = reason
    db.session.commit()
    log_action("VOID", "Payments", row.id,
               f"{row.payment_ref}; {row.casual.name}; {reason}; {len(linked)} attendance entries released")
    flash("Payment voided. Its attendance entries are unpaid again.")
    return redirect(url_for("payments"))


@app.route("/payment-receipt/<int:id>")
@permission_required("payments")
def payment_receipt(id):
    return render_template("payment_receipt.html", row=Payment.query.get_or_404(id))


@app.route("/audit")
@login_required
def audit_enhanced():
    if session.get("role") != "Admin":
        abort(403)
    query = AuditLog.query
    module = request.args.get("module", "").strip()
    action = request.args.get("action", "").strip()
    username = request.args.get("username", "").strip()
    if module:
        query = query.filter(AuditLog.module.ilike(f"%{module}%"))
    if action:
        query = query.filter(AuditLog.action == action)
    if username:
        query = query.filter(AuditLog.username.ilike(f"%{username}%"))
    rows = query.order_by(AuditLog.id.desc()).limit(1000).all()
    return render_template("audit.html", rows=rows,
                           filters={"module": module, "action": action, "username": username})


@app.errorhandler(403)
def forbidden(_):
    return render_template("403.html"), 403

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
