"""Read-only, company-isolated full reconciliation to Google Sheets.

Run from Render Cron with DATABASE_URL and GOOGLE_APPLICATION_CREDENTIALS.
Never writes to ERP tables. Google Sheets is a reporting replica.
"""
import os
import sys
import time
import logging
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from sqlalchemy import select

from app import app, db, Company

LOG = logging.getLogger("sheets_sync")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
API = "https://sheets.googleapis.com/v4/spreadsheets"
CONFIG = (
    ("STANCOFF_LEGACY_SHEET_ID", "legacy", (
        ("Suppliers", "supplier"), ("Purchases", "purchase"),
        ("Batches", "batch"), ("Processing", "processing"),
        ("Drying", "drying"), ("Inventory", "coffee_stock"),
        ("Inventory Movements", "coffee_movement"),
        ("Station Transfers", "station_transfer"),
        ("Sales", "sale"), ("Dispatch", "dispatch"),
        ("Casual Labour", "casual"), ("Attendance", "attendance"),
        ("Payments", "payment"),
    )),
    ("MHS_SHEET_ID", "mhs", (
        ("Suppliers", "mhs_supplier"), ("Purchases", "mhs_purchase"),
        ("Lots", "mhs_lot"), ("Drying", "mhs_drying"),
        ("Analysis", "mhs_analysis"), ("Production", "mhs_production"),
        ("Production Lots", "mhs_production_lot"),
        ("Inventory", "mhs_inventory_stock"),
        ("Inventory Movements", "mhs_inventory_movement"),
        ("Inventory Adjustments", "mhs_inventory_adjustment"),
    )),
    ("STANCOFF_COMMERCIAL_SHEET_ID", "commercial", (
        ("Suppliers", "mhs_supplier"), ("Purchases", "mhs_purchase"),
        ("Lots", "mhs_lot"), ("Drying", "mhs_drying"),
        ("Analysis", "mhs_analysis"), ("Production", "mhs_production"),
        ("Production Lots", "mhs_production_lot"),
        ("Inventory", "mhs_inventory_stock"),
        ("Inventory Movements", "mhs_inventory_movement"),
        ("Inventory Adjustments", "mhs_inventory_adjustment"),
    )),
)

# Do not publish staff/user identifiers, telephone numbers or free-text notes by default.
OMIT = {"phone", "buyer_phone", "driver_phone", "notes", "void_reason",
        "created_by", "processed_by", "dried_by", "supervisor", "details",
        "reason", "difference_reason", "receipt_notes", "username", "user_id",
        "created_at", "updated_at", "driver_name", "buyer_name", "authorized_by",
        "received_by", "dispatched_by", "moved_by"}
MAX_ROWS = 75000


def request(session, method, url, **kwargs):
    for attempt in range(5):
        response = session.request(method, url, timeout=90, **kwargs)
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 4:
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        return response.json() if response.content else {}
    raise RuntimeError("Sheets API retry limit reached")


def cell(value):
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float, bool)):
        return value
    value = str(value)
    # RAW writes prevent formula execution; keep text as text.
    return value[:40000]


def resolve_company(kind):
    if kind == "legacy":
        matches = Company.query.filter_by(is_legacy_stancoff=True).all()
    elif kind == "mhs":
        matches = Company.query.filter(db.func.lower(Company.code) == "mhs").all()
    else:
        matches = Company.query.filter(
            db.func.lower(Company.name).in_([
                "stancoff company limited commercial", "stancoff commercial"
            ])
        ).all()
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {kind} company, found {len(matches)}. Refusing to mix data.")
    return matches[0]


def extract(table_name, company_id=None):
    table = db.metadata.tables[table_name]
    cols = [c for c in table.columns if c.name not in OMIT]
    if company_id is not None and "company_id" not in table.columns:
        raise RuntimeError(f"Missing company isolation on {table_name}")
    stmt = select(*cols).select_from(table)
    if company_id is not None:
        stmt = stmt.where(table.c.company_id == company_id)
    if "id" in table.columns:
        stmt = stmt.order_by(table.c.id)
    rows = db.session.execute(stmt).all()
    if len(rows) > MAX_ROWS:
        raise RuntimeError(f"{table_name} has more than {MAX_ROWS} rows; refusing truncated export")
    return [[c.name for c in cols]] + [[cell(v) for v in row] for row in rows]


def sync_workbook(session, spreadsheet_id, company, tabs, scoped):
    base = f"{API}/{quote(spreadsheet_id, safe='')}"
    metadata = request(session, "GET", base, params={"fields": "sheets(properties(sheetId,title,gridProperties))"})
    existing = {s["properties"]["title"]: s["properties"] for s in metadata.get("sheets", [])}
    add = [{"addSheet": {"properties": {"title": title, "gridProperties": {"rowCount": 1000, "columnCount": 26, "frozenRowCount": 1}}}}
           for title, _ in tabs if title not in existing]
    if add:
        request(session, "POST", base + ":batchUpdate", json={"requests": add})
        metadata = request(session, "GET", base, params={"fields": "sheets(properties(sheetId,title,gridProperties))"})
        existing = {s["properties"]["title"]: s["properties"] for s in metadata.get("sheets", [])}
    for title, table in tabs:
        data = extract(table, company.id if scoped else None)
        props = existing[title]
        width = len(data[0])
        old_rows = props["gridProperties"].get("rowCount", 1000)
        old_cols = props["gridProperties"].get("columnCount", 26)
        # Clear stale rows after edits/deletions, then replace by stable database ID order.
        if len(data) > old_rows or width > old_cols:
            request(session, "POST", base + ":batchUpdate", json={"requests": [
                {"updateSheetProperties": {
                    "properties": {"sheetId": props["sheetId"], "gridProperties": {
                        "rowCount": max(old_rows, len(data)), "columnCount": max(old_cols, width)}},
                    "fields": "gridProperties.rowCount,gridProperties.columnCount"}}
            ]})
        a1 = quote(f"'{title.replace(chr(39), chr(39)*2)}'!A1", safe="")
        request(session, "POST", base + "/values/" + a1 + ":clear", json={})
        for start in range(0, len(data), 500):
            block = data[start:start + 500]
            destination = quote(f"'{title}'!A{start + 1}", safe="")
            request(session, "PUT", base + "/values/" + destination,
                    params={"valueInputOption": "RAW"}, json={"values": block})
        LOG.info("%s / %s: %s records", company.name, title, len(data) - 1)


def main():
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL missing: no sync performed")
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path or not os.path.isfile(credentials_path):
        raise RuntimeError("Google credential secret file missing: no sync performed")
    missing = [key for key, _, _ in CONFIG if not os.environ.get(key)]
    if missing:
        raise RuntimeError("Missing workbook IDs: " + ", ".join(missing))
    credentials = service_account.Credentials.from_service_account_file(credentials_path, scopes=SCOPE)
    session = AuthorizedSession(credentials)
    with app.app_context():
        for key, kind, tabs in CONFIG:
            company = resolve_company(kind)
            sync_workbook(session, os.environ[key], company, tabs, scoped=(kind != "legacy"))
    LOG.info("All company workbooks synchronized successfully")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        LOG.exception("Sheets synchronization failed")
        sys.exit(1)
