from flask import Blueprint, jsonify, request

from ..business import compute_holdings, current_qty_for_asset
from ..db import execute, query_all, query_one
from ..errors import NotFoundError, ValidationError
from ..routes.portfolios import get_portfolio_or_404
from ..security import require_admin, require_tab
from ..utils import new_id, normalize_jalali, now_ts

bp = Blueprint("transactions", __name__)


def _txn_public(row) -> dict:
    return {
        "id": row["id"], "portfolioId": row["portfolio_id"], "ts": row["ts"],
        "type": row["type"], "date": row["date"], "asset": row["asset"], "category": row["category"],
        "qty": row["qty"], "price": row["price"], "amount": row["amount"],
        "location": row["location"], "note": row["note"],
    }


def _txns_for_portfolio_as_dicts(pid: str, exclude_id: str | None = None) -> list[dict]:
    rows = query_all("SELECT * FROM transactions WHERE portfolio_id = ?", (pid,))
    return [dict(r) for r in rows if exclude_id is None or r["id"] != exclude_id]


def _prices_dict() -> dict[str, float]:
    rows = query_all("SELECT asset, price FROM prices")
    return {r["asset"]: r["price"] for r in rows}


@bp.get("/portfolios/<pid>/transactions")
@require_tab("holdings")
def list_transactions(pid):
    get_portfolio_or_404(pid)
    asset = request.args.get("asset")
    sql = "SELECT * FROM transactions WHERE portfolio_id = ?"
    params: list = [pid]
    if asset:
        sql += " AND asset = ?"
        params.append(asset)
    sql += " ORDER BY date ASC, ts ASC"
    rows = query_all(sql, tuple(params))
    return jsonify([_txn_public(r) for r in rows])


def _validate_and_upsert(pid: str, body: dict, exclude_id: str | None = None) -> dict:
    ttype = body.get("type")
    if ttype not in ("buy", "sell", "dividend"):
        raise ValidationError("نوع تراکنش باید یکی از خرید/فروش/سود نقدی باشد.")
    date = normalize_jalali(body.get("date") or "")
    if not date:
        raise ValidationError("فرمت تاریخ درست نیست.")
    asset = (body.get("asset") or "").strip()
    if not asset:
        raise ValidationError("نام دارایی لازم است.")
    category = (body.get("category") or "سایر").strip() or "سایر"
    amount = float(body.get("amount") or 0)
    qty = float(body.get("qty") or 0) if ttype != "dividend" else 0.0
    price = float(body.get("price") or 0) if ttype != "dividend" else 0.0
    location = (body.get("location") or "").strip()
    note = (body.get("note") or "").strip()

    if ttype in ("buy", "sell") and qty <= 0:
        raise ValidationError("تعداد باید بزرگ‌تر از صفر باشد.")
    if amount <= 0:
        raise ValidationError("مبلغ باید بزرگ‌تر از صفر باشد.")

    if ttype == "sell":
        existing_txns = _txns_for_portfolio_as_dicts(pid, exclude_id=exclude_id)
        available = current_qty_for_asset(asset, existing_txns, _prices_dict())
        if qty > available + 1e-6:
            raise ValidationError(
                f"تعداد فروش ({qty}) از موجودی «{asset}» ({available}) بیشتر است."
            )

    return {
        "type": ttype, "date": date, "asset": asset, "category": category,
        "qty": qty, "price": price, "amount": amount, "location": location, "note": note,
    }


@bp.post("/portfolios/<pid>/transactions")
@require_admin
def create_transaction(pid):
    get_portfolio_or_404(pid)
    body = request.get_json(silent=True) or {}
    clean = _validate_and_upsert(pid, body)
    tid = new_id()
    execute(
        "INSERT INTO transactions (id, portfolio_id, ts, type, date, asset, category, qty, price, amount, location, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (tid, pid, now_ts(), clean["type"], clean["date"], clean["asset"], clean["category"],
         clean["qty"], clean["price"], clean["amount"], clean["location"], clean["note"]),
    )
    return jsonify(_txn_public(query_one("SELECT * FROM transactions WHERE id = ?", (tid,)))), 201


def get_txn_or_404(tid: str):
    row = query_one("SELECT * FROM transactions WHERE id = ?", (tid,))
    if row is None:
        raise NotFoundError("تراکنش یافت نشد.")
    return row


@bp.put("/transactions/<tid>")
@require_admin
def update_transaction(tid):
    txn = get_txn_or_404(tid)
    body = request.get_json(silent=True) or {}
    clean = _validate_and_upsert(txn["portfolio_id"], body, exclude_id=tid)
    execute(
        "UPDATE transactions SET type=?, date=?, asset=?, category=?, qty=?, price=?, amount=?, location=?, note=? "
        "WHERE id = ?",
        (clean["type"], clean["date"], clean["asset"], clean["category"], clean["qty"],
         clean["price"], clean["amount"], clean["location"], clean["note"], tid),
    )
    return jsonify(_txn_public(query_one("SELECT * FROM transactions WHERE id = ?", (tid,))))


@bp.delete("/transactions/<tid>")
@require_admin
def delete_transaction(tid):
    get_txn_or_404(tid)
    # Mirrors the frontend's warning/behavior: if this sell produced a "سیو سود" withdrawal
    # (withdrawals.source_txn_id -> this txn), deleting the sell also deletes that withdrawal,
    # so the ladder rung goes back to "سیو‌نشده" instead of pointing at a sale that no longer exists.
    # IMPORTANT: capture the linked withdrawal ids BEFORE deleting the transaction — the FK's
    # ON DELETE SET NULL fires as part of that delete, which would otherwise clear
    # source_txn_id first and make a post-delete lookup by source_txn_id find nothing.
    linked = query_all("SELECT id FROM withdrawals WHERE source_txn_id = ?", (tid,))
    linked_ids = [row["id"] for row in linked]
    execute("DELETE FROM transactions WHERE id = ?", (tid,))
    for wid in linked_ids:
        execute("DELETE FROM withdrawals WHERE id = ?", (wid,))
    return jsonify({"ok": True, "unlinkedWithdrawals": len(linked_ids)})
