"""Stancoff startup wrapper.

Keeps the administrator inventory reconciliation tool while leaving the
application's normal station-transfer route untouched.
"""
from flask import request, redirect, url_for, flash, render_template_string
import app as stancoff

app = stancoff.app


@app.route('/admin/inventory-reconcile', methods=['GET', 'POST'])
@stancoff.login_required
def inventory_reconcile():
    if stancoff.session.get('role') != 'Admin':
        stancoff.abort(403)

    if request.method == 'POST':
        drying_id = request.form.get('drying_id', type=int)
        expected_weight = request.form.get('expected_weight', type=float)
        reason = (request.form.get('reason') or '').strip()
        row = stancoff.db.session.get(stancoff.Drying, drying_id) if drying_id else None
        if not row or expected_weight is None or expected_weight < 0 or not reason:
            flash('Enter a valid drying record, confirmed dry weight and reconciliation reason.')
            return redirect(url_for('inventory_reconcile'))

        stocks = stancoff.CoffeeStock.query.filter_by(drying_id=row.id).all()
        current = sum(float(s.weight or 0) for s in stocks)
        difference = round(float(expected_weight) - current, 6)
        if abs(difference) <= 0.0001:
            flash(f'No reconciliation required. Current inventory already equals {current:,.2f} kg.')
            return redirect(url_for('inventory_reconcile'))
        if difference < 0:
            flash('This tool currently restores missing stock only. Use the normal movement/stock correction workflow for reductions.')
            return redirect(url_for('inventory_reconcile'))

        location_name = (row.drying_location or '').strip()
        q = stancoff.Location.query.filter(stancoff.func.lower(stancoff.Location.name) == location_name.lower())
        if row.processing and row.processing.station_id:
            q = q.filter(stancoff.Location.station_id == row.processing.station_id)
        location = q.first()
        if not location:
            flash('The original drying location could not be resolved. No inventory was changed.')
            return redirect(url_for('inventory_reconcile'))

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
        stancoff.log_action('RECONCILE', 'Inventory', movement.id,
                            f'{row.batch.batch_no} {row.grade}: +{difference:,.2f} kg; {reason}')
        flash(f'Inventory reconciled by +{difference:,.2f} kg. The adjustment is recorded in movement history.')
        return redirect(url_for('inventory'))

    rows = stancoff.Drying.query.filter_by(status='Active').order_by(stancoff.Drying.id.desc()).all()
    balances = {}
    for row in rows:
        balances[row.id] = sum(float(s.weight or 0) for s in stancoff.CoffeeStock.query.filter_by(drying_id=row.id).all())
    return render_template_string('''
    {% extends "base.html" %}
    {% block title %}Inventory Reconciliation · Stancoff{% endblock %}
    {% block page_title %}Inventory reconciliation{% endblock %}
    {% block page_subtitle %}Admin-only correction when confirmed dry weight and live inventory do not agree{% endblock %}
    {% block content %}
    <section class="panel processing-intro">
      <div><span class="eyebrow">Stock control</span><h2>Reconcile missing dry stock</h2><p>This does not rewrite drying or transfer history. It creates an audited inventory adjustment at the original drying location.</p></div>
      <a class="secondary-button" href="{{ url_for('inventory') }}">Back to inventory</a>
    </section>
    <form method="post" class="panel processing-form">
      <label class="form-wide">Drying record
        <select name="drying_id" required>
          <option value="">Select drying record</option>
          {% for r in rows %}<option value="{{ r.id }}">{{ r.batch.batch_no }} · {{ r.grade }} · {{ r.drying_no }} · report dry {{ '{:,.2f}'.format(r.dry_weight or 0) }} kg · inventory {{ '{:,.2f}'.format(balances.get(r.id,0)) }} kg</option>{% endfor %}
        </select>
      </label>
      <label>Confirmed total dry weight (kg)<input type="number" step="0.01" min="0" name="expected_weight" required></label>
      <label class="form-wide">Reason<textarea name="reason" rows="3" required placeholder="Example: Restore missing Grade A dry balance after report/inventory mismatch"></textarea></label>
      <div class="form-wide"><button class="primary-button">Reconcile inventory</button></div>
    </form>
    {% endblock %}
    ''', rows=rows, balances=balances)
