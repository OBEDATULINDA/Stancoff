"""Filtered purchase reporting for legacy Stancoff."""
from datetime import datetime
from io import BytesIO
from flask import request, render_template, send_file
import xlsxwriter


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
        return render_template("purchase_report.html", rows=rows,
            suppliers=s.Supplier.query.filter_by(status="Active").order_by(s.Supplier.name).all(),
            batches=s.Batch.query.filter_by(status="Active").order_by(s.Batch.batch_no.desc()).all(),
            total_qty=total_qty, total_amount=total_amount, weighted_price=weighted_price,
            filters=request.args)

    @app.route("/reports/purchases/download.xlsx")
    @s.login_required
    @s.permission_required("purchases")
    def purchase_report_excel():
        rows = filtered_rows()
        output = BytesIO()
        wb = xlsxwriter.Workbook(output, {"in_memory": True})
        ws = wb.add_worksheet("Purchases")
        title = wb.add_format({"bold": True, "font_size": 16})
        header = wb.add_format({"bold": True, "bg_color": "#173F35", "font_color": "white", "border": 1})
        money = wb.add_format({"num_format": '#,##0', "border": 1})
        number = wb.add_format({"num_format": '#,##0.00', "border": 1})
        cell = wb.add_format({"border": 1})
        total_fmt = wb.add_format({"bold": True, "top": 2, "num_format": '#,##0.00'})
        total_money = wb.add_format({"bold": True, "top": 2, "num_format": '#,##0'})

        ws.write("A1", "STANCOFF PURCHASE REPORT", title)
        raw_from = (request.args.get("from_date") or "").strip()
        raw_to = (request.args.get("to_date") or "").strip()
        ws.write("A2", f"Period: {raw_from or 'Beginning'} to {raw_to or 'Latest'}")
        headers = ["Date","Batch Number","Supplier Code","Supplier","Process Type","Good Quantity (kg)",
                   "Floaters (kg)","Total Quantity (kg)","Cherry Price/kg","Floater Price/kg","Amount Paid (UGX)","Receipt"]
        for col, value in enumerate(headers):
            ws.write(3, col, value, header)
        for row_no, r in enumerate(rows, start=4):
            good = float(r.good_weight or 0)
            floaters = float(r.floaters_weight or 0)
            ws.write_datetime(row_no, 0, datetime.combine(r.purchase_date, datetime.min.time()), wb.add_format({"num_format":"dd-mmm-yyyy","border":1}))
            ws.write(row_no, 1, r.batch.batch_no, cell)
            ws.write(row_no, 2, r.supplier.code, cell)
            ws.write(row_no, 3, r.supplier.name, cell)
            ws.write(row_no, 4, r.batch.process_type or "", cell)
            ws.write_number(row_no, 5, good, number)
            ws.write_number(row_no, 6, floaters, number)
            ws.write_number(row_no, 7, good + floaters, number)
            ws.write_number(row_no, 8, float(r.cherry_price or 0), money)
            ws.write_number(row_no, 9, float(getattr(r, "floater_price", 0) or 0), money)
            ws.write_number(row_no, 10, float(r.total_amount or 0), money)
            ws.write(row_no, 11, r.receipt_no or "", cell)
        total_row = 4 + len(rows)
        total_qty = sum(float(r.good_weight or 0) + float(r.floaters_weight or 0) for r in rows)
        total_amount = sum(float(r.total_amount or 0) for r in rows)
        ws.write(total_row, 0, "TOTAL", total_fmt)
        ws.write_number(total_row, 7, total_qty, total_fmt)
        ws.write_number(total_row, 10, total_amount, total_money)
        ws.freeze_panes(4, 0)
        ws.autofilter(3, 0, max(3, total_row - 1), len(headers)-1)
        ws.set_column("A:A", 14); ws.set_column("B:C", 16); ws.set_column("D:D", 28)
        ws.set_column("E:E", 16); ws.set_column("F:H", 18); ws.set_column("I:K", 18); ws.set_column("L:L", 18)
        wb.close()
        output.seek(0)
        return send_file(output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True, download_name="stancoff_purchase_report.xlsx")
