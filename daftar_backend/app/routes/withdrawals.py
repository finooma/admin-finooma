from flask import Blueprint, jsonify, request

from ..db import execute, query_all, query_one
from ..errors import NotFoundError, ValidationError
from ..routes.portfolios import get_portfolio_or_404
from ..security import require_admin, require_tab
from ..utils import new_id, normalize_jalali, now_ts

bp = Blueprint("withdrawals", __name__)


def _wd_public(row) -> dict:
    return {
        "id": row["id"], "portfolioId": row["portfolio_id"], "ts": row["ts"],
        "category": row["category"], "date": row["date"], "amount": row["amount"],
        "dest": row["dest"], "note": row["note"], "level": row["level"],
        "sourceTxnId": row["source_txn_id"],
    }


@bp.get("/portfolios/<pid>/withdrawals")
@require_tab("ladders")
def list_withdrawals(pid):
    get_portfolio_or_404(pid)
    category = request.args.get("category")
    sql = "SELECT * FROM withdrawals WHERE portfolio_id = ?"
    params: list = [pid]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY date DESC, ts DESC"
    rows = query_all(sql, tuple(params))
    return jsonify([_wd_public(r) for r in rows])


@bp.post("/portfolios/<pid>/withdrawals")
@require_admin
def create_withdrawal(pid):
    """Manual withdrawal registration — for withdrawals that weren't backed by a real sell.
    (When profit comes from an actual sale, the frontend/UX steers admins toward the
    "🔒 سیو سود" flow — see secure_profit.py — which records both the sell and the withdrawal.)"""
    get_portfolio_or_404(pid)
    body = request.get_json(silent=True) or {}
    category = (body.get("category") or "").strip()
    if not category:
        raise ValidationError("کتگوری لازم است.")
    date = normalize_jalali(body.get("date") or "")
    if not date:
        raise ValidationError("فرمت تاریخ درست نیست.")
    amount = float(body.get("amount") or 0)
    if amount <= 0:
        raise ValidationError("مبلغ باید بزرگ‌تر از صفر باشد.")
    dest = (body.get("dest") or "").strip()
    note = (body.get("note") or "").strip()
    level = body.get("level")
    level = int(level) if level is not None else None

    wid = new_id()
    execute(
        "INSERT INTO withdrawals (id, portfolio_id, ts, category, date, amount, dest, note, level, source_txn_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
        (wid, pid, now_ts(), category, date, amount, dest, note, level),
    )
    return jsonify(_wd_public(query_one("SELECT * FROM withdrawals WHERE id = ?", (wid,)))), 201


@bp.delete("/withdrawals/<wid>")
@require_admin
def delete_withdrawal(wid):
    row = query_one("SELECT * FROM withdrawals WHERE id = ?", (wid,))
    if row is None:
        raise NotFoundError("برداشت یافت نشد.")
    execute("DELETE FROM withdrawals WHERE id = ?", (wid,))
    return jsonify({"ok": True})
