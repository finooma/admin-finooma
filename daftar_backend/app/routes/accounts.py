import datetime

from flask import Blueprint, jsonify, request

from ..business import compute_account_balance
from ..db import execute, get_db, query_all, query_one
from ..errors import NotFoundError, ValidationError
from ..security import require_admin, require_tab
from ..utils import new_id, normalize_jalali, now_ts

# Accounts are GLOBAL — shared across every portfolio, exactly like a real bank account isn't
# "owned" by one of this app's logical portfolios. One flat blueprint is enough now; there's no
# more /api/portfolios/<pid>/accounts nesting.
bp = Blueprint("accounts", __name__)


def _account_balance(account_row) -> float:
    movements = [dict(r) for r in query_all("SELECT * FROM cash_movements WHERE account_id = ?", (account_row["id"],))]
    txns = [dict(r) for r in query_all(
        "SELECT * FROM transactions WHERE account_id = ? AND type IN ('buy','sell','dividend')", (account_row["id"],)
    )]
    return compute_account_balance(account_row["opening_balance"], movements, txns)


def _account_public(row) -> dict:
    return {
        "id": row["id"], "name": row["name"],
        "openingBalance": row["opening_balance"], "createdAt": row["created_at"],
        "balance": _account_balance(row),
    }


def get_account_or_404(aid: str):
    row = query_one("SELECT * FROM accounts WHERE id = ?", (aid,))
    if row is None:
        raise NotFoundError("حساب یافت نشد.")
    return row


@bp.get("")
@require_tab("holdings")
def list_accounts():
    rows = query_all("SELECT * FROM accounts ORDER BY created_at ASC")
    return jsonify([_account_public(r) for r in rows])


@bp.post("")
@require_admin
def create_account():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        raise ValidationError("نام حساب لازم است.")
    opening_balance = float(body.get("openingBalance") or 0)
    aid = new_id()
    execute(
        "INSERT INTO accounts (id, name, opening_balance, created_at) VALUES (?, ?, ?, ?)",
        (aid, name, opening_balance, datetime.date.today().isoformat()),
    )
    return jsonify(_account_public(query_one("SELECT * FROM accounts WHERE id = ?", (aid,)))), 201


@bp.put("/<aid>")
@require_admin
def update_account(aid):
    get_account_or_404(aid)
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        raise ValidationError("نام حساب لازم است.")
    opening_balance = float(body.get("openingBalance") or 0)
    execute("UPDATE accounts SET name = ?, opening_balance = ? WHERE id = ?", (name, opening_balance, aid))
    return jsonify(_account_public(query_one("SELECT * FROM accounts WHERE id = ?", (aid,))))


@bp.delete("/<aid>")
@require_admin
def delete_account(aid):
    get_account_or_404(aid)
    in_use = query_one("SELECT COUNT(*) AS c FROM transactions WHERE account_id = ?", (aid,))["c"]
    mv_count = query_one("SELECT COUNT(*) AS c FROM cash_movements WHERE account_id = ?", (aid,))["c"]
    if in_use > 0 or mv_count > 0:
        raise ValidationError("این حساب سابقه‌ی تراکنش یا واریز/برداشت دارد و قابل حذف نیست.")
    execute("DELETE FROM accounts WHERE id = ?", (aid,))
    return jsonify({"ok": True})


def _movement_public(row) -> dict:
    return {
        "id": row["id"], "accountId": row["account_id"], "ts": row["ts"], "type": row["type"],
        "date": row["date"], "amount": row["amount"], "note": row["note"],
        "transferGroupId": row["transfer_group_id"],
    }


@bp.get("/<aid>/movements")
@require_tab("holdings")
def list_movements(aid):
    get_account_or_404(aid)
    rows = query_all("SELECT * FROM cash_movements WHERE account_id = ? ORDER BY date DESC, ts DESC", (aid,))
    return jsonify([_movement_public(r) for r in rows])


def _validate_movement_body(body: dict) -> tuple[str, float, str]:
    date = normalize_jalali(body.get("date") or "")
    if not date:
        raise ValidationError("فرمت تاریخ درست نیست.")
    amount = float(body.get("amount") or 0)
    if amount <= 0:
        raise ValidationError("مبلغ باید بزرگ‌تر از صفر باشد.")
    note = (body.get("note") or "").strip()
    return date, amount, note


@bp.post("/<aid>/deposit")
@require_admin
def deposit(aid):
    get_account_or_404(aid)
    body = request.get_json(silent=True) or {}
    date, amount, note = _validate_movement_body(body)
    mid = new_id()
    execute(
        "INSERT INTO cash_movements (id, account_id, ts, type, date, amount, note, transfer_group_id) "
        "VALUES (?, ?, ?, 'deposit', ?, ?, ?, NULL)",
        (mid, aid, now_ts(), date, amount, note),
    )
    return jsonify(_account_public(query_one("SELECT * FROM accounts WHERE id = ?", (aid,)))), 201


@bp.post("/<aid>/withdraw")
@require_admin
def withdraw(aid):
    account = get_account_or_404(aid)
    body = request.get_json(silent=True) or {}
    date, amount, note = _validate_movement_body(body)
    balance = _account_balance(account)
    if amount > balance + 1e-6:
        raise ValidationError(f"مبلغ برداشت ({amount}) از موجودی این حساب ({balance}) بیشتر است.")
    mid = new_id()
    execute(
        "INSERT INTO cash_movements (id, account_id, ts, type, date, amount, note, transfer_group_id) "
        "VALUES (?, ?, ?, 'withdraw', ?, ?, ?, NULL)",
        (mid, aid, now_ts(), date, amount, note),
    )
    return jsonify(_account_public(query_one("SELECT * FROM accounts WHERE id = ?", (aid,)))), 201


@bp.post("/transfer")
@require_admin
def transfer():
    """Moves cash between any two accounts (global now — no portfolio restriction), atomically
    (both rows are written together, or neither is)."""
    body = request.get_json(silent=True) or {}
    from_id = body.get("fromAccountId")
    to_id = body.get("toAccountId")
    if not from_id or not to_id or from_id == to_id:
        raise ValidationError("حساب مبدا و مقصد باید متفاوت و معتبر باشند.")
    from_acc = get_account_or_404(from_id)
    get_account_or_404(to_id)
    date, amount, note = _validate_movement_body(body)
    balance = _account_balance(from_acc)
    if amount > balance + 1e-6:
        raise ValidationError(f"مبلغ انتقال ({amount}) از موجودی حساب مبدا ({balance}) بیشتر است.")

    group_id = new_id()
    ts = now_ts()
    db = get_db()
    try:
        db.execute("BEGIN")
        db.execute(
            "INSERT INTO cash_movements (id, account_id, ts, type, date, amount, note, transfer_group_id) "
            "VALUES (?, ?, ?, 'transfer_out', ?, ?, ?, ?)",
            (new_id(), from_id, ts, date, amount, note, group_id),
        )
        db.execute(
            "INSERT INTO cash_movements (id, account_id, ts, type, date, amount, note, transfer_group_id) "
            "VALUES (?, ?, ?, 'transfer_in', ?, ?, ?, ?)",
            (new_id(), to_id, ts, date, amount, note, group_id),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return jsonify({
        "ok": True,
        "from": _account_public(query_one("SELECT * FROM accounts WHERE id = ?", (from_id,))),
        "to": _account_public(query_one("SELECT * FROM accounts WHERE id = ?", (to_id,))),
    }), 201
