"""Unified legacy Stancoff reporting: purchase, processing and dry production."""
from datetime import datetime
from io import BytesIO
from flask import request, render_template, redirect, url_for, abort, send_file, flash
import xlsxwriter

def register_report_center(app, s):
    def permitted(kind):
        allowed = s.ROLE_PERMISSIONS.get(s.session.get("role"), set())
        permission = "purchases" if kind == "purchase" else "reports"
        return "*" in allowed or permission in allowed

    def date_value(name):
        raw = (request.args.get(name) or "").strip()
        return datetime.strptime(raw, "%Y-%m-%d").date() if raw else None

    @app.route("/reports")
    @s.login_required
    def report_center():
        kinds = [k for k in ("purchase", "processing", "production") if permitted(k)]
        if not kinds:
            abort(403)
        selected = request.args.get("report_type", kinds[0])
        if selected not in kinds:
            selected = kinds[0]
        return render_template("report_center.html", kinds=kinds, selected=selected,
            filters=request.args,
            batches=s.Batch.query.order_by(s.Batch.batch_no.desc()).all(),
            suppliers=s.Supplier.query.filter_by(status="Active").order_by(s.Supplier.name).all(),
            stations=s.Station.query.filter_by(status="Active").order_by(s.Station.name).all(),
            process_types=[x[0] for x in s.db.session.query(s.Batch.process_type).distinct().order_by(s.Batch.process_type).all() if x[0]])

    @app.route("/reports/download.xlsx")
    @s.login_required
    def report_center_excel():
        kind = request.args.get("report_type", "")
        if kind not in ("purchase", "processing", "production"):
            abort(400)
        if not permitted(kind):
            abort(403)
        if kind == "purchase":
            return redirect(url_for("purchase_report_excel", **{k:v for k,v in request.args.items() if k != "report_type"}))
        if kind == "processing":
            args = {k:v for k,v in request.args.items() if k not in ("report_type", "supplier_id", "grade", "batch_id")}
            if request.args.get("batch_id"):
                batch = s.db.session.get(s.Batch, request.args.get("batch_id", type=int))
                if batch:
                    args["batch_no"] = batch.batch_no
            if request.args.get("from_date"): args["start_date"] = request.args["from_date"]
            if request.args.get("to_date"): args["end_date"] = request.args["to_date"]
            return redirect(url_for("processing_reports_excel", **args))

        try:
            from_date, to_date = date_value("from_date"), date_value("to_date")
        except ValueError:
            flash("Enter valid dates in YYYY-MM-DD format.")
            return redirect(url_for("report_center", report_type=kind))
        if from_date and to_date and from_date > to_date:
            flash("From date must not be later than To date.")
            return redirect(url_for("report_center", report_type=kind))

        query = s.Drying.query.filter(s.Drying.status == "Active")
        if from_date: query = query.filter(s.Drying.start_date >= from_date)
        if to_date: query = query.filter(s.Drying.start_date <= to_date)
        if request.args.get("batch_id", type=int):
            query = query.filter(s.Drying.batch_id == request.args.get("batch_id", type=int))
        if request.args.get("grade"):
            query = query.filter(s.Drying.grade == request.args["grade"])
        if request.args.get("station_id", type=int):
            query = query.join(s.Processing, s.Drying.processing_id == s.Processing.id).filter(s.Processing.station_id == request.args.get("station_id", type=int))
        if request.args.get("process_type"):
            query = query.join(s.Batch, s.Drying.batch_id == s.Batch.id).filter(s.Batch.process_type == request.args["process_type"])
        rows = query.order_by(s.Drying.start_date, s.Drying.id).all()
        output = BytesIO()
        wb = xlsxwriter.Workbook(output, {"in_memory": True})
        ws = wb.add_worksheet("Dry Production")
        title = wb.add_format({"bold":True,"font_size":16})
        header = wb.add_format({"bold":True,"bg_color":"#173F35","font_color":"white","border":1})
        number = wb.add_format({"num_format":"#,##0.00","border":1})
        textfmt = wb.add_format({"border":1})
        datefmt = wb.add_format({"num_format":"dd-mmm-yyyy","border":1})
        totalfmt = wb.add_format({"bold":True,"top":2,"num_format":"#,##0.00"})
        ws.write(0,0,"STANCOFF DRY PRODUCTION REPORT",title)
        ws.write(1,0,f"Period: {from_date or 'Beginning'} to {to_date or 'Latest'}")
        headings = ["Drying No","Batch","Process","Station","Grade","Start Date","End Date","Wet Input (kg)","Dry Output (kg)","Drying Loss (kg)","Outturn (%)","Moisture (%)","Progress"]
        for col,h in enumerate(headings): ws.write(3,col,h,header)
        for ri,r in enumerate(rows,4):
            vals = [r.drying_no,r.batch.batch_no,r.batch.process_type,r.processing.station.name if r.processing and r.processing.station else "",r.grade,r.start_date,r.end_date,float(r.input_weight or 0),float(r.dry_weight or 0),float(r.drying_loss or 0),float(r.outturn_percent or 0),r.moisture,r.drying_status]
            for col,val in enumerate(vals):
                if val is None: ws.write_blank(ri,col,None,textfmt)
                elif col in (5,6): ws.write_datetime(ri,col,datetime.combine(val,datetime.min.time()),datefmt)
                elif col in (7,8,9,10,11): ws.write_number(ri,col,float(val),number)
                else: ws.write(ri,col,val,textfmt)
        tr = len(rows)+4
        ws.write(tr,0,"TOTAL",totalfmt)
        for col in (7,8,9): ws.write_number(tr,col,sum(float(getattr(r, {7:"input_weight",8:"dry_weight",9:"drying_loss"}[col]) or 0) for r in rows),totalfmt)
        ws.freeze_panes(4,0)
        ws.autofilter(3,0,max(3,tr-1),len(headings)-1)
        ws.set_column(0,4,19);ws.set_column(5,6,16);ws.set_column(7,12,19)
        wb.close();output.seek(0)
        return send_file(output,as_attachment=True,download_name="stancoff_dry_production_report.xlsx",mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
