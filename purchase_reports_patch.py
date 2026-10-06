"""Filtered purchase reporting for legacy Stancoff."""
from datetime import datetime
from io import StringIO
import csv
from flask import request, render_template, Response, session


def register_purchase_reports(app, s):
    def filtered_rows():
        q = s.Purchase.query.filter_by(status="Active")
        raw_from = (request.args.get("from_date") or "").strip()
        raw_to = (request.args.get("to_date") or "").strip()
        supplier_id = request.args.get("supplier_id", type=int)
        batch_id = request.args.get("batch_id", type=int)
        process_type = (request.args.get("process_type") or "").strip()

        if raw_from:
            q = q.filter(s.Purchase.purchase_date >= datetime.strptime(raw_from, "%Y-%m-%d").date())
        if raw_to:
            q = q.filter(s.Purchase.purchase_date <= datetime.strptime(raw_to, "%Y-%m-%d").date())
        if supplier_id:
            q = q.filter(s.Purchase.supplier_id == supplier_id)
        if batch_id:
            q = q.filter(s.Purchase.batch_id == batch_id)
        if process_type:
            q = q.join(s.Batch, s.Purchase.batch_id == s.Batch.id).filter(s.Batch.process_type == process_type)
        return q.order_by(s.Purchase.purchase_date.asc(), s.Purchase.id.asc()).all()

    @app.route("/reports/purchases")
    @s.login_required
    @s.permission_required("purchases")
    def purchase_report():
        rows = filtered_rows()
        total_qty = sum(float(r.good_weight or 0) + float(r.floaters_weight or 0) for r in rows)
        total_amount = sum(float(r.total_amount or 0) for r in rows)
        weighted_price = total_amount / total_qty if total_qty else 0
        return render_template(
            "purchase_report.html", rows=rows,
            suppliers=s.Supplier.query.filter_by(status="Active").order_by(s.Supplier.name).all(),
            batches=s.Batch.query.filter_by(status="Active").order_by(s.Batch.batch_no.desc()).all(),
            total_qty=total_qty, total_amount=total_amount, weighted_price=weighted_price,
            filters=request.args
        )

    @app.route("/reports/purchases/download.csv")
    @s.login_required
    @s.permission_required("purchases")
    def purchase_report_csv():
        rows = filtered_rows()
        out = StringIO()
        w = csv.writer(out)
        w.writerow(["Date","Batch Number","Supplier Code","Supplier","Process Type","Good Quantity (kg)","Floaters (kg)","Total Quantity (kg)","Cherry Price/kg","Floater Price/kg","Amount Paid (UGX)","Receipt"])
        for r in rows:
            good = float(r.good_weight or 0)
            floaters = float(r.floaters_weight or 0)
            w.writerow([
                r.purchase_date.isoformat(), r.batch.batch_no, r.supplier.code, r.supplier.name,
                r.batch.process_type, f"{good:.2f}", f"{floaters:.2f}", f"{good+floaters:.2f}",
                f"{float(r.cherry_price or 0):.2f}", f"{float(r.floaters_price or 0):.2f}",
                f"{float(r.total_amount or 0):.2f}", r.receipt_no or ""
            ])
        total_qty = sum(float(r.good_weight or 0)+float(r.floaters_weight or 0) for r in rows)
        total_amount = sum(float(r.total_amount or 0) for r in rows)
        w.writerow([])
        w.writerow(["TOTAL","","","","","", "", f"{total_qty:.2f}","","",f"{total_amount:.2f}",""])
        filename = "stancoff_purchase_report.csv"
        return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition":f"attachment; filename={filename}"})
