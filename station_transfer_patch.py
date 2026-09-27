"""Safe patch for Stancoff cherry station transfers.

Fixes dispatch inventory deduction so the exact selected dry-stock weight is removed
from the source balance. The original route referenced an undefined source_weight.
"""


def apply(s):
    def station_transfers():
        s.ensure_initial_stock()
        if s.request.method == "POST":
            source_ids = s.request.form.getlist("source_stock_id[]")
            destination_ids = s.request.form.getlist("to_location_id[]")
            weights = s.request.form.getlist("weight[]")
            moistures = s.request.form.getlist("moisture[]")
            bags = s.request.form.getlist("number_of_bags[]")

            if not source_ids or not (len(source_ids) == len(destination_ids) == len(weights) == len(moistures) == len(bags)):
                s.flash("Add at least one complete coffee line to the transfer.")
                return s.redirect(s.url_for("station_transfers"))
            if len(set(source_ids)) != len(source_ids):
                s.flash("The same inventory balance cannot be selected twice on one transfer form.")
                return s.redirect(s.url_for("station_transfers"))

            prepared = []
            from_station_id = None
            to_station_id = None
            try:
                for index, source_id in enumerate(source_ids):
                    source = s.db.session.get(s.CoffeeStock, int(source_id))
                    destination = s.db.session.get(s.Location, int(destination_ids[index]))
                    if not source or not destination:
                        raise ValueError(f"Coffee line {index + 1} contains an invalid stock or destination.")
                    if not source.location.station_id or not destination.station_id:
                        raise ValueError(f"Coffee line {index + 1} must use locations linked to stations.")
                    if source.location.station_id == destination.station_id:
                        raise ValueError(f"Coffee line {index + 1} must move to a different station.")
                    if from_station_id is None:
                        from_station_id = source.location.station_id
                        to_station_id = destination.station_id
                    elif source.location.station_id != from_station_id or destination.station_id != to_station_id:
                        raise ValueError("All coffee lines on one transfer form must move between the same sending and receiving stations.")

                    weight = float(weights[index] or 0)
                    available = float(source.weight or 0)
                    if weight <= 0 or weight > available + 0.0001:
                        raise ValueError(f"Line {index + 1}: transfer weight must be above zero and cannot exceed {available:,.2f} kg.")
                    moisture = float(moistures[index]) if moistures[index] else source.moisture
                    bag_count = int(bags[index]) if bags[index] else None
                    prepared.append((source, destination, weight, moisture, bag_count))

                document = s.StationTransferDocument(
                    transfer_no=s.next_code(s.StationTransferDocument, "transfer_no", "TRF", 6),
                    transfer_date=s.datetime.strptime(s.request.form["transfer_date"], "%Y-%m-%d").date(),
                    from_station_id=from_station_id,
                    to_station_id=to_station_id,
                    vehicle_no=s.request.form.get("vehicle_no"),
                    driver_name=s.request.form.get("driver_name"),
                    driver_phone=s.request.form.get("driver_phone"),
                    dispatch_time=s.request.form.get("dispatch_time"),
                    arrival_time=s.request.form.get("arrival_time"),
                    dispatched_by=s.request.form.get("dispatched_by"),
                    received_by=s.request.form.get("received_by"),
                    authorized_by=s.request.form.get("authorized_by"),
                    remarks=s.request.form.get("remarks"),
                    status="In Transit",
                    created_by=s.session.get("username"),
                )
                s.db.session.add(document)
                s.db.session.flush()

                total_weight = 0
                for source, destination, weight, moisture, bag_count in prepared:
                    # Deduct exactly the dry-stock quantity selected on this transfer line.
                    source.weight = max(0, float(source.weight or 0) - weight)

                    movement = s.CoffeeMovement(
                        movement_no=s.next_code(s.CoffeeMovement, "movement_no", "MOV", 6),
                        drying_id=source.drying_id, batch_id=source.batch_id, grade=source.grade,
                        from_location_id=source.location_id, to_location_id=destination.id,
                        movement_date=document.transfer_date, weight=weight, moisture=moisture,
                        movement_type="Station Transfer", reason=document.remarks,
                        moved_by=document.dispatched_by, created_by=s.session.get("username")
                    )
                    s.db.session.add(movement)
                    s.db.session.flush()
                    s.db.session.add(s.StationTransferItem(document_id=document.id, movement_id=movement.id, number_of_bags=bag_count))
                    batch = s.db.session.get(s.Batch, source.batch_id)
                    if batch:
                        batch.status = "Transferred to " + destination.station.name
                    total_weight += weight

                s.db.session.commit()
                s.log_action("CREATE", "Station Transfer", document.id, f"{document.transfer_no}: {len(prepared)} lines, {total_weight:,.2f} kg")
                s.flash(f"{document.transfer_no} dispatched with {len(prepared)} coffee lines totalling {total_weight:,.2f} kg. It is awaiting receipt at {document.to_station.name}.")
                return s.redirect(s.url_for("station_transfer_document_print", id=document.id))
            except (ValueError, TypeError) as exc:
                s.db.session.rollback()
                s.flash(str(exc))
                return s.redirect(s.url_for("station_transfers"))
            except Exception:
                s.db.session.rollback()
                s.app.logger.exception("Station transfer save failed")
                s.flash("The station transfer could not be saved. No inventory was changed. Please review the lines and try again.")
                return s.redirect(s.url_for("station_transfers"))

        stocks = s.CoffeeStock.query.join(s.Location).filter(
            s.CoffeeStock.weight > 0.0001, s.Location.station_id.isnot(None)
        ).order_by(s.CoffeeStock.updated_at.desc()).all()
        destinations = s.Location.query.join(s.Station).filter(
            s.Location.status == "Active", s.Station.status == "Active"
        ).order_by(s.Station.name, s.Location.location_type, s.Location.name).all()
        documents = s.StationTransferDocument.query.order_by(s.StationTransferDocument.id.desc()).limit(200).all()
        legacy_rows = s.StationTransfer.query.order_by(s.StationTransfer.id.desc()).limit(100).all()
        return s.render_template(
            "station_transfers.html", stocks=stocks, destinations=destinations,
            documents=documents, legacy_rows=legacy_rows,
            next_transfer=s.next_code(s.StationTransferDocument, "transfer_no", "TRF", 6)
        )

    # Keep the existing route/rules and replace only its view function.
    s.app.view_functions["station_transfers"] = station_transfers
