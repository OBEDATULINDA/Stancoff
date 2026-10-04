"""Stancoff startup wrapper.

Adds administrator inventory reconciliation and safely patches legacy Stancoff
station-transfer dispatch without replacing the large app.py file.
"""
from flask import request, redirect, url_for, flash, render_template_string
import app as stancoff

app = stancoff.app
_original_station_transfers = stancoff.station_transfers


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


def fixed_station_transfers():
    """Use the operator-entered actual loading weight as the dispatch deduction."""
    if request.method != 'POST':
        return _original_station_transfers()

    stancoff.ensure_initial_stock()
    source_ids = request.form.getlist('source_stock_id[]')
    destination_ids = request.form.getlist('to_location_id[]')
    weights = request.form.getlist('weight[]')
    moistures = request.form.getlist('moisture[]')
    bags = request.form.getlist('number_of_bags[]')
    if not source_ids or not (len(source_ids) == len(destination_ids) == len(weights) == len(moistures) == len(bags)):
        flash('Add at least one complete coffee line to the transfer.')
        return redirect(url_for('station_transfers'))
    if len(set(source_ids)) != len(source_ids):
        flash('The same inventory balance cannot be selected twice on one transfer form.')
        return redirect(url_for('station_transfers'))

    prepared = []
    from_station_id = None
    to_station_id = None
    try:
        for index, source_id in enumerate(source_ids):
            source = stancoff.db.session.get(stancoff.CoffeeStock, int(source_id))
            destination = stancoff.db.session.get(stancoff.Location, int(destination_ids[index]))
            if not source or not destination:
                raise ValueError(f'Coffee line {index + 1} contains an invalid stock or destination.')
            if not source.location.station_id or not destination.station_id:
                raise ValueError(f'Coffee line {index + 1} must use locations linked to stations.')
            if source.location.station_id == destination.station_id:
                raise ValueError(f'Coffee line {index + 1} must move to a different station.')
            if from_station_id is None:
                from_station_id = source.location.station_id
                to_station_id = destination.station_id
            elif source.location.station_id != from_station_id or destination.station_id != to_station_id:
                raise ValueError('All coffee lines on one transfer form must move between the same sending and receiving stations.')

            loading_weight = float(weights[index] or 0)
            system_available = float(source.weight or 0)
            if loading_weight <= 0 or loading_weight > system_available + 0.0001:
                raise ValueError(f'Line {index + 1}: actual loading weight must be above zero and cannot exceed {system_available:,.2f} kg available.')
            moisture = float(moistures[index]) if moistures[index] else source.moisture
            bag_count = int(bags[index]) if bags[index] else None
            prepared.append((source, destination, loading_weight, system_available, moisture, bag_count))

        document = stancoff.StationTransferDocument(
            transfer_no=stancoff.next_code(stancoff.StationTransferDocument, 'transfer_no', 'TRF', 6),
            transfer_date=stancoff.datetime.strptime(request.form['transfer_date'], '%Y-%m-%d').date(),
            from_station_id=from_station_id, to_station_id=to_station_id,
            vehicle_no=request.form.get('vehicle_no'), driver_name=request.form.get('driver_name'),
            driver_phone=request.form.get('driver_phone'), dispatch_time=request.form.get('dispatch_time'),
            arrival_time=request.form.get('arrival_time'), dispatched_by=request.form.get('dispatched_by'),
            received_by=request.form.get('received_by'), authorized_by=request.form.get('authorized_by'),
            remarks=request.form.get('remarks'), status='In Transit', created_by=stancoff.session.get('username'))
        stancoff.db.session.add(document)
        stancoff.db.session.flush()

        total_weight = 0
        for source, destination, loading_weight, system_available, moisture, bag_count in prepared:
            # Actual scale/loading weight is what physically leaves inventory.
            source.weight = max(0, system_available - loading_weight)
            movement = stancoff.CoffeeMovement(
                movement_no=stancoff.next_code(stancoff.CoffeeMovement, 'movement_no', 'MOV', 6),
                drying_id=source.drying_id, batch_id=source.batch_id, grade=source.grade,
                from_location_id=source.location_id, to_location_id=destination.id,
                movement_date=document.transfer_date, weight=loading_weight,
                source_weight=system_available, moisture=moisture,
                movement_type='Station Transfer', reason=document.remarks,
                moved_by=document.dispatched_by, created_by=stancoff.session.get('username'))
            stancoff.db.session.add(movement)
            stancoff.db.session.flush()
            stancoff.db.session.add(stancoff.StationTransferItem(
                document_id=document.id, movement_id=movement.id, number_of_bags=bag_count))
            batch = stancoff.db.session.get(stancoff.Batch, source.batch_id)
            if batch:
                batch.status = 'Transferred to ' + destination.station.name
            total_weight += loading_weight

        stancoff.db.session.commit()
        stancoff.log_action('CREATE', 'Station Transfer', document.id,
                            f'{document.transfer_no}: {len(prepared)} lines, actual loaded {total_weight:,.2f} kg')
        flash(f'{document.transfer_no} dispatched. Actual loading weight {total_weight:,.2f} kg was deducted from source inventory.')
        return redirect(url_for('station_transfer_document_print', id=document.id))
    except (ValueError, TypeError) as exc:
        stancoff.db.session.rollback()
        flash(str(exc))
        return redirect(url_for('station_transfers'))
    except Exception:
        stancoff.db.session.rollback()
        app.logger.exception('Station transfer save failed in bootstrap patch')
        flash('The station transfer could not be saved. No inventory was changed.')
        return redirect(url_for('station_transfers'))


# Replace only the registered view function; route URL and permissions remain unchanged.
app.view_functions['station_transfers'] = stancoff.permission_required('transfers')(fixed_station_transfers)
