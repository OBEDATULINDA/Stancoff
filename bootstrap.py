"""Stancoff startup wrapper.

Adds a small administrator-only reconciliation screen without replacing app.py.
The existing application remains the source of all normal operations.
"""
from flask import request, redirect, url_for, flash
import app as stancoff

app = stancoff.app


@app.route('/admin/inventory-reconcile', methods=['POST'])
@stancoff.login_required
def inventory_reconcile():
    if stancoff.session.get('role') != 'Admin':
        stancoff.abort(403)

    drying_id = request.form.get('drying_id', type=int)
    expected_weight = request.form.get('expected_weight', type=float)
    reason = (request.form.get('reason') or '').strip()
    row = stancoff.db.session.get(stancoff.Drying, drying_id) if drying_id else None
    if not row or expected_weight is None or expected_weight < 0 or not reason:
        flash('Enter a valid drying record, confirmed dry weight and reconciliation reason.')
        return redirect(request.referrer or url_for('drying'))

    stocks = stancoff.CoffeeStock.query.filter_by(drying_id=row.id).all()
    current = sum(float(s.weight or 0) for s in stocks)
    difference = round(float(expected_weight) - current, 6)
    if difference <= 0.0001:
        flash(f'No positive reconciliation required. Current inventory is {current:,.2f} kg.')
        return redirect(request.referrer or url_for('drying'))

    location_name = (row.drying_location or '').strip()
    q = stancoff.Location.query.filter(stancoff.func.lower(stancoff.Location.name) == location_name.lower())
    if row.processing and row.processing.station_id:
        q = q.filter(stancoff.Location.station_id == row.processing.station_id)
    location = q.first()
    if not location:
        flash('The original drying location could not be resolved. No inventory was changed.')
        return redirect(request.referrer or url_for('drying'))

    stock = stancoff.CoffeeStock.query.filter_by(drying_id=row.id, location_id=location.id).first()
    if not stock:
        stock = stancoff.CoffeeStock(
            drying_id=row.id, batch_id=row.batch_id, grade=row.grade,
            location_id=location.id, weight=0, moisture=row.moisture,
            stock_status='Fully Dry'
        )
        stancoff.db.session.add(stock)
    stock.weight = float(stock.weight or 0) + difference
    stock.stock_status = 'Fully Dry'

    movement = stancoff.CoffeeMovement(
        movement_no=stancoff.next_code(stancoff.CoffeeMovement, 'movement_no', 'MOV', 6),
        drying_id=row.id, batch_id=row.batch_id, grade=row.grade,
        from_location_id=location.id, to_location_id=location.id,
        movement_date=stancoff.datetime.utcnow().date(), weight=difference,
        source_weight=difference, moisture=row.moisture,
        movement_type='Inventory Reconciliation', reason=reason,
        moved_by=stancoff.session.get('username'), created_by=stancoff.session.get('username')
    )
    stancoff.db.session.add(movement)
    stancoff.db.session.commit()
    stancoff.log_action('RECONCILE', 'Inventory', movement.id, f'{row.batch.batch_no} {row.grade}: +{difference:,.2f} kg; {reason}')
    flash(f'Inventory reconciled by +{difference:,.2f} kg. The adjustment is recorded in movement history.')
    return redirect(request.referrer or url_for('inventory'))
