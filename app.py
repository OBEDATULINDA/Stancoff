
import os
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-in-production")
database_url = os.getenv("DATABASE_URL", "sqlite:///stancoff.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

ROLE_PERMISSIONS = {
    "Admin": {"*"},
    "Manager": {"dashboard","suppliers","prices","batches","purchases","casuals","rates","attendance","payments","reports"},
    "Receiving Clerk": {"dashboard","suppliers","batches","purchases"},
    "Processing Supervisor": {"dashboard","batches","reports"},
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
    stats = {
        "suppliers": Supplier.query.filter_by(status="Active").count(),
        "batches": Batch.query.filter_by(status="Open").count(),
        "purchases": Purchase.query.filter_by(status="Active").count(),
        "casuals": Casual.query.filter_by(status="Active").count(),
    }
    recent = Purchase.query.order_by(Purchase.id.desc()).limit(10).all()
    return render_template("dashboard.html", stats=stats, recent=recent)

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
