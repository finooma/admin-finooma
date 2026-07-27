import datetime
import json

from flask import Blueprint, jsonify, request

from ..business import category_agg, compute_holdings_for_portfolio, jalali_sort_key
from ..db import execute, query_all, query_one
from ..errors import ValidationError
from ..routes.portfolios import get_portfolio_or_404
from ..security import require_admin, require_tab
from ..utils import new_id, normalize_jalali

bp = Blueprint("snapshots", __name__)


def _snap_public(row) -> dict:
    return {
        "id": row["id"], "portfolioId": row["portfolio_id"], "date": row["date"],
        "investment": row["total_investment"], "value": row["total_value"],
        "unrealized": row["total_unrealized"], "realized": row["total_realized"],
        "overall": row["total_unrealized"] + row["total_realized"],
        "byCategory": json.loads(row["category_breakdown"]) if row["category_breakdown"] else {},
    }


@bp.get("/<pid>/snapshots")
@require_tab("trend")
def list_snapshots(pid):
    get_portfolio_or_404(pid)
    rows = query_all("SELECT * FROM snapshots WHERE portfolio_id = ?", (pid,))
    rows = sorted(rows, key=lambda r: jalali_sort_key(r["date"]))
    return jsonify([_snap_public(r) for r in rows])


@bp.post("/<pid>/snapshots")
@require_admin
def create_snapshot(pid):
    """Equivalent of onSaveSnapshot(): records one totals-per-category row for the trend chart,
    for the given date (defaults to today). Re-saving the same date for the same portfolio
    replaces the previous snapshot for that date (upsert), same as the frontend's
    'SNAPSHOTS = SNAPSHOTS.filter(not same date+portfolio) then push' logic."""
    get_portfolio_or_404(pid)
    body = request.get_json(silent=True) or {}
    date = normalize_jalali(body.get("date") or "") if body.get("date") else None
    if body.get("date") and not date:
        raise ValidationError("فرمت تاریخ درست نیست.")
    today = datetime.date.today().isoformat()
    date = date or today

    txns = [dict(r) for r in query_all("SELECT * FROM transactions WHERE portfolio_id = ?", (pid,))]
    prices = {r["asset"]: r["price"] for r in query_all("SELECT asset, price FROM prices")}
    result = compute_holdings_for_portfolio(txns, prices)
    agg = category_agg(result["holdings"], result["closed"])

    total_value = sum(c["value"] for c in agg.values())
    total_investment = sum(c["investment"] for c in agg.values())
    total_unrealized = sum(c["unrealized"] for c in agg.values())
    total_realized = sum(c["realized"] for c in agg.values())
    by_category = {cat: {"investment": c["investment"], "value": c["value"]} for cat, c in agg.items()}

    # Upsert: remove any existing snapshot for this exact (portfolio, date) first.
    execute("DELETE FROM snapshots WHERE portfolio_id = ? AND date = ?", (pid, date))

    sid = new_id()
    execute(
        "INSERT INTO snapshots (id, portfolio_id, date, total_value, total_investment, total_unrealized, total_realized, category_breakdown, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (sid, pid, date, total_value, total_investment, total_unrealized, total_realized, json.dumps(by_category), today),
    )
    return jsonify(_snap_public(query_one("SELECT * FROM snapshots WHERE id = ?", (sid,)))), 201


@bp.delete("/<pid>/snapshots/<path:date>")
@require_admin
def delete_snapshot_for_date(pid, date):
    """Deletes this portfolio's snapshot for one date — equivalent of deleteSnapshotsForDate()
    scoped to a single portfolio. (The frontend's "all portfolios" variant just calls this
    once per portfolio id.)"""
    get_portfolio_or_404(pid)
    cur = execute("DELETE FROM snapshots WHERE portfolio_id = ? AND date = ?", (pid, date))
    return jsonify({"ok": True, "deleted": cur.rowcount})
