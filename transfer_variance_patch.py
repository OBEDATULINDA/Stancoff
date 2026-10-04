"""Final station-transfer variance policy.

Actual loading weight is always accepted. Differences greater than 50 kg from the
system warehouse balance are flagged for review, but do not block dispatch.
"""
from flask import request, redirect, url_for, flash
import bootstrap

app = bootstrap.app
stancoff = bootstrap.stancoff
_original_get = bootstrap._original_station_transfers


def station_transfers_allow_flagged_variance():
    if request.method != 'POST':
        return _original_get()

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
            variance = loading_weight - system_available
            if loading_weight <= 0:
                raise ValueError(f'Line {index + 1}: actual loading weight must be above zero.')
            moisture = float(moistures[index]) if moistures[index] else source.moisture
            bag_count = int(bags[index]) if bags[index] else None
            prepared.append((source, destination, loading_weight, system_available, moisture, bag_count, variance))

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
        variance_notes = []
        flagged_notes = []
        for source, destination, loading_weight, system_available, moisture, bag_count, variance in prepared:
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

            label = f'{source.batch.batch_no if source.batch else source.batch_id} {source.grade}: {variance:+,.2f} kg'
            if abs(variance) > 0.0001:
                variance_notes.append(label)
            if abs(variance) > 50.0001:
                flagged_notes.append(label)

        stancoff.db.session.commit()
        detail = f'{document.transfer_no}: {len(prepared)} lines, actual loaded {total_weight:,.2f} kg'
        if variance_notes:
            detail += '; loading variance ' + ', '.join(variance_notes)
        if flagged_notes:
            detail += '; FLAGGED >50 kg: ' + ', '.join(flagged_notes)
        stancoff.log_action('CREATE', 'Station Transfer', document.id, detail)

        if flagged_notes:
            flash(f'⚠ {document.transfer_no} dispatched successfully. Variance above 50 kg FLAGGED for review: ' + ', '.join(flagged_notes) + '.')
        elif variance_notes:
            flash(f'{document.transfer_no} dispatched. Actual loading weight {total_weight:,.2f} kg recorded. Variance: ' + ', '.join(variance_notes) + '.')
        else:
            flash(f'{document.transfer_no} dispatched. Actual loading weight {total_weight:,.2f} kg recorded.')
        return redirect(url_for('station_transfer_document_print', id=document.id))
    except (ValueError, TypeError) as exc:
        stancoff.db.session.rollback()
        flash(str(exc))
        return redirect(url_for('station_transfers'))
    except Exception:
        stancoff.db.session.rollback()
        app.logger.exception('Station transfer save failed in variance patch')
        flash('The station transfer could not be saved. No inventory was changed.')
        return redirect(url_for('station_transfers'))


app.view_functions['station_transfers'] = stancoff.permission_required('transfers')(station_transfers_allow_flagged_variance)
