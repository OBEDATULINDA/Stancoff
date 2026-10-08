"""Stancoff startup wrapper.

Keeps the administrator inventory reconciliation tool and safely handles
station-transfer dispatch using the actual loading scale weight.
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


@app.before_request
def station_transfer_actual_loading_dispatch():
    """Handle only POST dispatches; normal GET page remains in app.py unchanged.

    Actual loading weight is authoritative. Any variance is accepted. Absolute
    variance above 50 kg is flagged for review but never blocks dispatch.
    """
    if request.endpoint != 'station_transfers' or request.method != 'POST':
        return None

    if not stancoff.session.get('user_id'):
        return redirect(url_for('login'))
    role = stancoff.session.get('role')
    allowed = stancoff.ROLE_PERMISSIONS.get(role, set())
    if '*' not in allowed and 'transfers' not in allowed:
        stancoff.abort(403)

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

            actual_weight = float(weights[index] or 0)
            if actual_weight <= 0:
                raise ValueError(f'Line {index + 1}: actual loading weight must be above zero.')
            system_weight = float(source.weight or 0)
            variance = actual_weight - system_weight
            moisture = float(moistures[index]) if moistures[index] else source.moisture
            bag_count = int(bags[index]) if bags[index] else None
            prepared.append((source, destination, actual_weight, system_weight, variance, moisture, bag_count))

        document = stancoff.StationTransferDocument(
            transfer_no=stancoff.next_code(stancoff.StationTransferDocument, 'transfer_no', 'TRF', 6),
            transfer_date=stancoff.datetime.strptime(request.form['transfer_date'], '%Y-%m-%d').date(),
            from_station_id=from_station_id,
            to_station_id=to_station_id,
            vehicle_no=request.form.get('vehicle_no'),
            driver_name=request.form.get('driver_name'),
            driver_phone=request.form.get('driver_phone'),
            dispatch_time=request.form.get('dispatch_time'),
            arrival_time=request.form.get('arrival_time'),
            dispatched_by=request.form.get('dispatched_by'),
            received_by=request.form.get('received_by'),
            authorized_by=request.form.get('authorized_by'),
            remarks=request.form.get('remarks'),
            status='In Transit',
            created_by=stancoff.session.get('username'),
        )
        stancoff.db.session.add(document)
        stancoff.db.session.flush()

        total_weight = 0.0
        flagged = []
        variances = []
        for source, destination, actual_weight, system_weight, variance, moisture, bag_count in prepared:
            # Never allow a negative stock balance. If the scale weight is above
            # system stock, all recorded stock leaves and the positive variance is
            # preserved on the movement/audit trail.
            source.weight = max(0.0, system_weight - actual_weight)

            variance_note = f'System {system_weight:,.2f} kg; actual loading {actual_weight:,.2f} kg; variance {variance:+,.2f} kg'
            movement_reason = (document.remarks or '').strip()
            movement_reason = f'{movement_reason} | {variance_note}' if movement_reason else variance_note
            movement = stancoff.CoffeeMovement(
                movement_no=stancoff.next_code(stancoff.CoffeeMovement, 'movement_no', 'MOV', 6),
                drying_id=source.drying_id,
                batch_id=source.batch_id,
                grade=source.grade,
                from_location_id=source.location_id,
                to_location_id=destination.id,
                movement_date=document.transfer_date,
                weight=actual_weight,
                source_weight=system_weight,
                moisture=moisture,
                movement_type='Station Transfer',
                reason=movement_reason,
                moved_by=document.dispatched_by,
                created_by=stancoff.session.get('username'),
            )
            stancoff.db.session.add(movement)
            stancoff.db.session.flush()
            stancoff.db.session.add(stancoff.StationTransferItem(
                document_id=document.id,
                movement_id=movement.id,
                number_of_bags=bag_count,
            ))
            batch = stancoff.db.session.get(stancoff.Batch, source.batch_id)
            if batch:
                batch.status = 'Transferred'  # Full destination is recorded on the transfer document.
            total_weight += actual_weight
            variances.append(variance)
            if abs(variance) > 50.0001:
                batch_label = source.batch.batch_no if source.batch else str(source.batch_id)
                flagged.append(f'{batch_label} {source.grade}: {variance:+,.2f} kg')

        stancoff.db.session.commit()
        detail = f'{document.transfer_no}: {len(prepared)} lines, actual loaded {total_weight:,.2f} kg; variances ' + ', '.join(f'{v:+,.2f}' for v in variances)
        if flagged:
            detail += '; FLAGGED >50 kg: ' + ', '.join(flagged)
        stancoff.log_action('CREATE', 'Station Transfer', document.id, detail)

        if flagged:
            flash(f'{document.transfer_no} dispatched successfully. FLAGGED for weight variance above 50 kg: ' + ', '.join(flagged) + '. Transfer was NOT rejected.')
        else:
            flash(f'{document.transfer_no} dispatched successfully using actual loading weight {total_weight:,.2f} kg.')
        return redirect(url_for('station_transfer_document_print', id=document.id))

    except (ValueError, TypeError) as exc:
        stancoff.db.session.rollback()
        flash(str(exc))
        return redirect(url_for('station_transfers'))
    except Exception:
        stancoff.db.session.rollback()
        app.logger.exception('Station transfer actual-loading dispatch failed')
        flash('The station transfer could not be saved. No inventory was changed.')
        return redirect(url_for('station_transfers'))


@app.route('/processing/<int:id>/unvoid', methods=['POST'])
@stancoff.permission_required('processing')
def processing_unvoid(id):
    record = stancoff.Processing.query.get_or_404(id)
    if record.status != 'Voided':
        flash('This processing record is already active.')
        return redirect(url_for('processing'))

    # A restored processing record must not conflict with another active
    # processing record for the same batch.
    other = stancoff.Processing.query.filter(
        stancoff.Processing.batch_id == record.batch_id,
        stancoff.Processing.status == 'Active',
        stancoff.Processing.id != record.id,
    ).first()
    if other:
        flash(f'Cannot restore {record.processing_no}: this batch already has active processing record {other.processing_no}.')
        return redirect(url_for('processing'))

    # Normally drying has to be voided before processing can be voided, but
    # retain this guard for older records/data corrections.
    active_drying = stancoff.Drying.query.filter_by(processing_id=record.id, status='Active').first()
    if active_drying:
        flash('Cannot restore this processing record while an active drying record is linked to it.')
        return redirect(url_for('processing'))

    record.status = 'Active'
    record.void_reason = None
    batch = stancoff.db.session.get(stancoff.Batch, record.batch_id)
    if batch and batch.status == 'Open':
        batch.status = 'Processing'
    stancoff.db.session.commit()
    stancoff.log_action('UNVOID', 'Processing', record.id, record.processing_no)
    flash(f'{record.processing_no} restored successfully. You can now open Edit if any processing details need changing.')
    return redirect(url_for('processing'))


@app.route('/drying/<int:id>/unvoid', methods=['POST'])
@stancoff.permission_required('drying')
def drying_unvoid(id):
    row = stancoff.Drying.query.get_or_404(id)
    if row.status != 'Voided':
        flash('This drying record is already active.')
        return redirect(url_for('drying'))

    if not row.processing or row.processing.status != 'Active':
        flash('Restore the linked processing record first before restoring this drying record.')
        return redirect(url_for('drying'))

    conflict = stancoff.Drying.query.filter(
        stancoff.Drying.processing_id == row.processing_id,
        stancoff.Drying.grade == row.grade,
        stancoff.Drying.status == 'Active',
        stancoff.Drying.id != row.id,
    ).first()
    if conflict:
        flash(f'Cannot restore {row.drying_no}: {row.grade} already has active drying record {conflict.drying_no}.')
        return redirect(url_for('drying'))

    # Voiding drying does not remove its stock/movement history, so restoring
    # must reactivate the same record only. Never recreate inventory here.
    row.status = 'Active'
    row.void_reason = None
    stancoff.refresh_drying_completion(row)
    if row.batch:
        if row.drying_status == 'Completed':
            has_final = stancoff.CoffeeStock.query.join(stancoff.Location).filter(
                stancoff.CoffeeStock.drying_id == row.id,
                stancoff.CoffeeStock.weight > 0.0001,
                stancoff.Location.location_type == 'Final Warehouse',
            ).first()
            row.batch.status = 'Stored' if has_final else 'Temporary Storage'
        else:
            row.batch.status = 'Drying'
    stancoff.db.session.commit()
    stancoff.log_action('UNVOID', 'Drying', row.id, row.drying_no)
    flash(f'{row.drying_no} restored successfully. Existing inventory and movement history were preserved.')
    return redirect(url_for('drying'))
