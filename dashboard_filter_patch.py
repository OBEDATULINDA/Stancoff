"""Custom reporting-period support for the legacy Stancoff operations dashboard."""
from datetime import datetime, timedelta
from flask import request, render_template


def register_dashboard_filter(app, s):
    @app.before_request
    def custom_dashboard_period_filter():
        if request.endpoint != 'dashboard' or request.method != 'GET':
            return None
        raw_from = (request.args.get('from_date') or '').strip()
        raw_to = (request.args.get('to_date') or '').strip()
        if not raw_from and not raw_to:
            return None

        try:
            from_date = datetime.strptime(raw_from, '%Y-%m-%d').date() if raw_from else None
            to_date = datetime.strptime(raw_to, '%Y-%m-%d').date() if raw_to else datetime.utcnow().date()
        except ValueError:
            return None
        if from_date and to_date and from_date > to_date:
            from_date, to_date = to_date, from_date

        def in_period(value):
            if not value:
                return False
            return (not from_date or value >= from_date) and (not to_date or value <= to_date)

        purchases = [p for p in s.Purchase.query.filter_by(status='Active').order_by(s.Purchase.purchase_date.asc()).all() if in_period(p.purchase_date)]
        processing = [r for r in s.Processing.query.filter_by(status='Active').order_by(s.Processing.processing_date.asc()).all() if in_period(r.processing_date)]
        drying = [r for r in s.Drying.query.filter_by(status='Active').order_by(s.Drying.start_date.asc()).all() if in_period(r.start_date)]
        movements_all = s.CoffeeMovement.query.filter_by(status='Active').order_by(s.CoffeeMovement.movement_date.asc()).all()
        movements = [m for m in movements_all if in_period(m.movement_date)]
        stocks = s.CoffeeStock.query.filter(s.CoffeeStock.weight > 0).all()

        gross = sum(float(p.gross_weight or 0) for p in purchases)
        good = sum(float(p.good_weight or 0) for p in purchases)
        floaters = sum(float(p.floaters_weight or 0) for p in purchases)
        spend = sum(float(p.total_amount or 0) for p in purchases)
        cherry_value = sum(float(p.good_weight or 0) * float(p.cherry_price or 0) for p in purchases)
        avg_price = cherry_value / good if good else 0
        supplier_ids = {p.supplier_id for p in purchases}

        completed_drying = [r for r in drying if r.drying_status == 'Completed' and r.dry_weight is not None]
        proc_out = [float(r.outturn_percent or 0) for r in processing if float(r.input_weight or 0) > 0]
        dry_out = [float(r.outturn_percent or 0) for r in completed_drying if float(r.input_weight or 0) > 0]

        stock_by_type = {'Drying Area': 0.0, 'Temporary Storage': 0.0, 'Final Warehouse': 0.0}
        grade_inventory, location_inventory = {}, {}
        for stock in stocks:
            w = float(stock.weight or 0)
            grade_inventory[stock.grade] = grade_inventory.get(stock.grade, 0) + w
            name = stock.location.name if stock.location else 'Unknown'
            location_inventory[name] = location_inventory.get(name, 0) + w
            typ = stock.location.location_type if stock.location else 'Unknown'
            stock_by_type[typ] = stock_by_type.get(typ, 0) + w

        stats = {
            'suppliers': len(supplier_ids), 'open_batches': s.Batch.query.filter(s.Batch.status.in_(['Open','Processing','Drying'])).count(),
            'purchases': len(purchases), 'gross_weight': gross, 'good_weight': good, 'floaters_weight': floaters,
            'total_spend': spend, 'average_cherry_price': avg_price, 'average_cherry_price_kg': good,
            'current_stock': sum(float(x.weight or 0) for x in stocks),
            'temporary_stock': stock_by_type.get('Temporary Storage',0), 'final_stock': stock_by_type.get('Final Warehouse',0),
            'drying_stock': stock_by_type.get('Drying Area',0),
            'processing_outturn': sum(proc_out)/len(proc_out) if proc_out else 0,
            'drying_outturn': sum(dry_out)/len(dry_out) if dry_out else 0, 'movements': len(movements),
        }

        supplier_totals, area_totals, monthly_totals, process_totals = {}, {}, {}, {}
        for p in purchases:
            w, value = float(p.good_weight or 0), float(p.total_amount or 0)
            sup = p.supplier
            row = supplier_totals.setdefault(sup.id, {'name':sup.name,'code':sup.code,'weight':0.0,'deliveries':0,'value':0.0})
            row['weight'] += w; row['deliveries'] += 1; row['value'] += value
            area = (sup.location or '').strip() or 'Unspecified'
            ar = area_totals.setdefault(area, {'area':area,'weight':0.0,'deliveries':0}); ar['weight'] += w; ar['deliveries'] += 1
            month = p.purchase_date.strftime('%Y-%m')
            mr = monthly_totals.setdefault(month, {'month':month,'weight':0.0,'value':0.0}); mr['weight'] += w; mr['value'] += value
            process = p.batch.process_type or 'Unspecified'; process_totals[process] = process_totals.get(process,0) + w

        top_suppliers = sorted(supplier_totals.values(), key=lambda r:r['weight'], reverse=True)[:8]
        areas = sorted(area_totals.values(), key=lambda r:r['weight'], reverse=True)[:8]
        months = sorted(monthly_totals.values(), key=lambda r:r['month'])[-12:]
        locations = sorted(location_inventory.items(), key=lambda r:r[1], reverse=True)[:10]
        outturn = sorted([{'batch':r.batch.batch_no,'outturn':float(r.outturn_percent or 0)} for r in processing], key=lambda r:r['batch'])[-10:]
        charts = {
            'monthly': {'labels':[r['month'] for r in months], 'weights':[round(r['weight'],2) for r in months], 'values':[round(r['value'],2) for r in months]},
            'areas': {'labels':[r['area'] for r in areas], 'weights':[round(r['weight'],2) for r in areas]},
            'processes': {'labels':list(process_totals.keys()), 'weights':[round(v,2) for v in process_totals.values()]},
            'grades': {'labels':list(grade_inventory.keys()), 'weights':[round(v,2) for v in grade_inventory.values()]},
            'locations': {'labels':[r[0] for r in locations], 'weights':[round(r[1],2) for r in locations]},
            'outturn': {'labels':[r['batch'] for r in outturn], 'values':[round(r['outturn'],2) for r in outturn]},
        }
        return render_template('dashboard.html', period='custom', from_date=from_date, to_date=to_date, stats=stats,
            recent=list(reversed(purchases[-6:])), recent_movements=list(reversed(movements[-8:])),
            top_suppliers=top_suppliers, alerts=[], charts=charts, workforce_notices=[])
