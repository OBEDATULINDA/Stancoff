
import os
from datetime import datetime
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
    "Manager": {"dashboard","suppliers","prices","batches","purchases","processing","drying","casuals","rates","attendance","payments","reports"},
    "Receiving Clerk": {"dashboard","suppliers","batches","purchases"},
    "Processing Supervisor": {"dashboard","batches","processing","drying","reports"},
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
    # Load active purchases once and aggregate in Python.
    # This avoids database-specific GROUP BY/date functions and works on both
    # PostgreSQL (Render) and SQLite (local testing).
    active_rows = Purchase.query.filter_by(status="Active").order_by(Purchase.purchase_date.asc()).all()

    total_good = sum(float(p.good_weight or 0) for p in active_rows)
    total_spend = sum(float(p.total_amount or 0) for p in active_rows)

    stats = {
        "suppliers": Supplier.query.filter_by(status="Active").count(),
        "batches": Batch.query.filter_by(status="Open").count(),
        "purchases": len(active_rows),
        "casuals": Casual.query.filter_by(status="Active").count(),
        "good_weight": total_good,
        "total_spend": total_spend,
    }

    recent = list(reversed(active_rows[-8:]))

    supplier_totals = {}
    area_totals = {}
    monthly_totals = {}
    batch_totals = {}

    for p in active_rows:
        supplier = p.supplier
        batch = p.batch
        weight = float(p.good_weight or 0)
        value = float(p.total_amount or 0)

        supplier_key = supplier.id
        if supplier_key not in supplier_totals:
            supplier_totals[supplier_key] = {
                "name": supplier.name,
                "code": supplier.code,
                "weight": 0.0,
                "deliveries": 0,
                "value": 0.0,
            }
        supplier_totals[supplier_key]["weight"] += weight
        supplier_totals[supplier_key]["deliveries"] += 1
        supplier_totals[supplier_key]["value"] += value

        area = (supplier.location or "").strip() or "Unspecified"
        if area not in area_totals:
            area_totals[area] = {"area": area, "weight": 0.0, "deliveries": 0}
        area_totals[area]["weight"] += weight
        area_totals[area]["deliveries"] += 1

        month = p.purchase_date.strftime("%Y-%m")
        if month not in monthly_totals:
            monthly_totals[month] = {"month": month, "weight": 0.0, "value": 0.0}
        monthly_totals[month]["weight"] += weight
        monthly_totals[month]["value"] += value

        batch_key = batch.id
        if batch_key not in batch_totals:
            batch_totals[batch_key] = {
                "batch_no": batch.batch_no,
                "process_type": batch.process_type,
                "weight": 0.0,
                "deliveries": 0,
            }
        batch_totals[batch_key]["weight"] += weight
        batch_totals[batch_key]["deliveries"] += 1

    top_suppliers = sorted(
        supplier_totals.values(), key=lambda r: r["weight"], reverse=True
    )[:10]
    area_rows = sorted(
        area_totals.values(), key=lambda r: r["weight"], reverse=True
    )[:10]
    monthly_rows = sorted(
        monthly_totals.values(), key=lambda r: r["month"]
    )[-12:]
    batch_rows = sorted(
        batch_totals.values(), key=lambda r: r["weight"], reverse=True
    )[:10]

    charts = {
        "suppliers": {
            "labels": [f'{r["code"]} - {r["name"]}' for r in top_suppliers],
            "weights": [round(r["weight"], 2) for r in top_suppliers],
            "deliveries": [r["deliveries"] for r in top_suppliers],
        },
        "areas": {
            "labels": [r["area"] for r in area_rows],
            "weights": [round(r["weight"], 2) for r in area_rows],
        },
        "monthly": {
            "labels": [r["month"] for r in monthly_rows],
            "weights": [round(r["weight"], 2) for r in monthly_rows],
            "values": [round(r["value"], 2) for r in monthly_rows],
        },
        "batches": {
            "labels": [r["batch_no"] for r in batch_rows],
            "weights": [round(r["weight"], 2) for r in batch_rows],
        },
    }

    return render_template(
        "dashboard.html",
        stats=stats,
        recent=recent,
        top_suppliers=top_suppliers,
        area_rows=area_rows,
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
        cid = int(request.form["casual_id"]); rr = get_rate(cid, d)
        if not rr:
            flash("Add a rate first."); return redirect(url_for("attendance"))
        amount = rr.daily_rate if request.form["work_type"] == "Full Day" else rr.daily_rate/2
        a = Attendance(work_date=d, casual_id=cid, work_done=request.form.get("work_done"),
                       work_type=request.form["work_type"], rate=rr.daily_rate, amount=amount)
        db.session.add(a); db.session.commit(); log_action("CREATE","Attendance",a.id)
        return redirect(url_for("attendance"))
    return render_template("attendance.html", rows=Attendance.query.order_by(Attendance.id.desc()).all(),
                           casuals=Casual.query.filter_by(status="Active").order_by(Casual.name).all())

@app.route("/payments", methods=["GET","POST"])
@permission_required("payments")
def payments():
    if request.method == "POST":
        cid = int(request.form["casual_id"])
        start = datetime.strptime(request.form["period_start"], "%Y-%m-%d").date()
        end = datetime.strptime(request.form["period_end"], "%Y-%m-%d").date()
        entries = Attendance.query.filter(
            Attendance.casual_id==cid, Attendance.work_date>=start,
            Attendance.work_date<=end, Attendance.status=="Unpaid").all()
        gross = sum(x.amount for x in entries)
        deduction = float(request.form.get("deduction") or 0)
        p = Payment(payment_ref=next_code(Payment,"payment_ref","PAY",6), casual_id=cid,
                    period_start=start, period_end=end, gross_pay=gross, deduction=deduction,
                    net_paid=max(0,gross-deduction),
                    payment_date=datetime.strptime(request.form["payment_date"], "%Y-%m-%d").date(),
                    method=request.form["method"])
        db.session.add(p)
        for x in entries:
            x.status="Paid"; x.payment_ref=p.payment_ref
        db.session.commit(); log_action("CREATE","Payments",p.id,p.payment_ref)
        return redirect(url_for("payments"))
    return render_template("payments.html", rows=Payment.query.order_by(Payment.id.desc()).all(),
                           casuals=Casual.query.filter_by(status="Active").order_by(Casual.name).all())

@app.route("/payment-receipt/<int:id>")
@permission_required("payments")
def payment_receipt(id):
    return render_template("payment_receipt.html", row=Payment.query.get_or_404(id))

@app.errorhandler(403)
def forbidden(_):
    return render_template("403.html"), 403

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
