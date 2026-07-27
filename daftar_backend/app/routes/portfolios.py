import datetime

from flask import Blueprint, jsonify, request

from ..db import execute, query_all, query_one
from ..errors import NotFoundError, ValidationError
from ..security import require_auth, require_admin
from ..utils import new_id

bp = Blueprint("portfolios", __name__)


def _portfolio_public(row) -> dict:
    return {"id": row["id"], "name": row["name"], "createdAt": row["created_at"]}


def get_portfolio_or_404(pid: str):
    row = query_one("SELECT * FROM portfolios WHERE id = ?", (pid,))
    if row is None:
        raise NotFoundError("سبد یافت نشد.")
    return row


@bp.get("")
@require_auth
def list_portfolios():
    rows = query_all("SELECT * FROM portfolios ORDER BY created_at ASC")
    return jsonify([_portfolio_public(r) for r in rows])


@bp.post("")
@require_admin
def create_portfolio():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        raise ValidationError("نام سبد لازم است.")
    pid = new_id()
    execute(
        "INSERT INTO portfolios (id, name, created_at) VALUES (?, ?, ?)",
        (pid, name, datetime.date.today().isoformat()),
    )
    return jsonify(_portfolio_public(query_one("SELECT * FROM portfolios WHERE id = ?", (pid,)))), 201


@bp.put("/<pid>")
@require_admin
def update_portfolio(pid):
    get_portfolio_or_404(pid)
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        raise ValidationError("نام سبد لازم است.")
    execute("UPDATE portfolios SET name = ? WHERE id = ?", (name, pid))
    return jsonify(_portfolio_public(query_one("SELECT * FROM portfolios WHERE id = ?", (pid,))))


@bp.delete("/<pid>")
@require_admin
def delete_portfolio(pid):
    get_portfolio_or_404(pid)
    if query_all("SELECT 1 FROM portfolios") and query_one("SELECT COUNT(*) AS c FROM portfolios")["c"] <= 1:
        raise ValidationError("حداقل یک سبد باید در سامانه باقی بماند.")
    txn_count = query_one("SELECT COUNT(*) AS c FROM transactions WHERE portfolio_id = ?", (pid,))["c"]
    if txn_count > 0:
        raise ValidationError(
            f"این سبد {txn_count} تراکنش دارد و قابل حذف نیست. ابتدا تراکنش‌های آن را حذف کنید."
        )
    # ON DELETE CASCADE (see schema.sql) takes care of that portfolio's withdrawals,
    # snapshots, and ladder rows — transactions are already confirmed empty above.
    execute("DELETE FROM portfolios WHERE id = ?", (pid,))
    return jsonify({"ok": True})
