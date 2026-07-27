from flask import Blueprint, jsonify, request

from ..business import category_agg, compute_holdings_for_portfolio, current_qty_for_asset, ladder_levels_with_defaults
from ..db import get_db, query_all
from ..errors import ValidationError
from ..routes.portfolios import get_portfolio_or_404
from ..security import require_admin
from ..utils import new_id, normalize_jalali, now_ts

bp = Blueprint("secure_profit", __name__)


def _txns_for_portfolio(pid: str) -> list[dict]:
    return [dict(r) for r in query_all("SELECT * FROM transactions WHERE portfolio_id = ?", (pid,))]


def _prices_dict() -> dict[str, float]:
    return {r["asset"]: r["price"] for r in query_all("SELECT asset, price FROM prices")}


def _stored_levels(pid: str, cat: str) -> list[dict] | None:
    rows = query_all(
        "SELECT idx, threshold_pct, withdraw_pct FROM ladders WHERE portfolio_id = ? AND category = ? ORDER BY idx",
        (pid, cat),
    )
    if not rows:
        return None
    return [{"t": r["threshold_pct"], "w": r["withdraw_pct"]} for r in rows]


@bp.post("/<pid>/secure-profit")
@require_admin
def secure_profit(pid):
    """Turns one ladder rung's suggested withdrawal into a real sell — atomically writing both
    a 'sell' transaction and a withdrawal linked to it (source_txn_id), exactly matching
    openSecureProfitModal's submit handler in the frontend. If validation fails partway
    through, nothing is written (single DB transaction, rolled back on error).

    Body: {"category": str, "levelIdx": int, "asset": str, "date": "YYYY/MM/DD",
           "price": float, "qty": float, "amount": float, "location": str,
           "note": str (optional), "dest": str (optional)}
    """
    get_portfolio_or_404(pid)
    body = request.get_json(silent=True) or {}

    category = (body.get("category") or "").strip()
    if not category:
        raise ValidationError("کتگوری لازم است.")
    level_idx = body.get("levelIdx")
    if level_idx is None:
        raise ValidationError("شماره پله (levelIdx) لازم است.")
    level_idx = int(level_idx)

    levels = ladder_levels_with_defaults(category, _stored_levels(pid, category))
    if level_idx < 0 or level_idx >= len(levels):
        raise ValidationError("پله‌ی نامعتبر است.")
    lv = levels[level_idx]

    asset = (body.get("asset") or "").strip()
    if not asset:
        raise ValidationError("دارایی لازم است.")
    date = normalize_jalali(body.get("date") or "")
    if not date:
        raise ValidationError("فرمت تاریخ درست نیست.")
    price = float(body.get("price") or 0)
    qty = float(body.get("qty") or 0)
    amount = float(body.get("amount") or 0)
    location = (body.get("location") or "").strip()
    dest = (body.get("dest") or "").strip()
    note = (body.get("note") or f"سیو سود — پله {level_idx + 1} (آستانه {lv['t']}٪) کتگوری {category}").strip()

    if qty <= 0:
        raise ValidationError("تعداد فروش باید بزرگ‌تر از صفر باشد.")
    if amount <= 0:
        raise ValidationError("مبلغ فروش باید بزرگ‌تر از صفر باشد.")

    existing_txns = _txns_for_portfolio(pid)
    available = current_qty_for_asset(asset, existing_txns, _prices_dict())
    if qty > available + 1e-6:
        raise ValidationError(f"تعداد فروش ({qty}) از موجودی «{asset}» ({available}) بیشتر است.")

    # Confirm this category actually has open holdings to sell from (mirrors openSecureProfitModal's
    # guard, which refuses to open at all if catHoldings is empty).
    result = compute_holdings_for_portfolio(existing_txns, _prices_dict())
    cat_holdings = [h for h in result["holdings"] if h["category"] == category and h["qty"] > 1e-9]
    if not cat_holdings:
        raise ValidationError("دارایی بازی در این کتگوری برای فروش وجود ندارد.")

    sell_txn_id = new_id()
    withdrawal_id = new_id()
    ts = now_ts()

    db = get_db()
    try:
        db.execute("BEGIN")
        db.execute(
            "INSERT INTO transactions (id, portfolio_id, ts, type, date, asset, category, qty, price, amount, location, note) "
            "VALUES (?, ?, ?, 'sell', ?, ?, ?, ?, ?, ?, ?, ?)",
            (sell_txn_id, pid, ts, date, asset, category, qty, price, amount, location, note),
        )
        db.execute(
            "INSERT INTO withdrawals (id, portfolio_id, ts, category, date, amount, dest, note, level, source_txn_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (withdrawal_id, pid, ts, category, date, amount, dest, f"از فروش {asset}", level_idx, sell_txn_id),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return jsonify({
        "ok": True,
        "sellTransactionId": sell_txn_id,
        "withdrawalId": withdrawal_id,
        "message": "فروش ثبت شد و سود این پله سیو شد.",
    }), 201
