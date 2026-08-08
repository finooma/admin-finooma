import datetime

from flask import Blueprint, jsonify, request

from ..db import execute, query_all, query_one
from ..errors import NotFoundError, ValidationError
from ..security import require_admin, require_auth
from ..utils import new_id

bp = Blueprint("categories", __name__)


def _cat_public(row) -> dict:
    return {"id": row["id"], "name": row["name"], "isDefault": bool(row["is_default"]), "createdAt": row["created_at"]}


@bp.get("")
@require_auth
def list_categories():
    rows = query_all("SELECT * FROM categories ORDER BY is_default DESC, name ASC")
    return jsonify([_cat_public(r) for r in rows])


@bp.post("")
@require_admin
def create_category():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        raise ValidationError("نام کتگوری لازم است.")
    if query_one("SELECT 1 FROM categories WHERE lower(name) = lower(?)", (name,)):
        raise ValidationError("این نام کتگوری قبلاً استفاده شده.")
    cid = new_id()
    execute(
        "INSERT INTO categories (id, name, is_default, created_at) VALUES (?, ?, 0, ?)",
        (cid, name, datetime.date.today().isoformat()),
    )
    return jsonify(_cat_public(query_one("SELECT * FROM categories WHERE id = ?", (cid,)))), 201


def get_category_or_404(cid: str):
    row = query_one("SELECT * FROM categories WHERE id = ?", (cid,))
    if row is None:
        raise NotFoundError("کتگوری یافت نشد.")
    return row


@bp.put("/<cid>")
@require_admin
def rename_category(cid):
    """Renaming here instantly applies everywhere — every transaction, ladder rung, and
    withdrawal references category_id, never the name, so nothing else needs to change."""
    get_category_or_404(cid)
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        raise ValidationError("نام کتگوری لازم است.")
    dupe = query_one("SELECT 1 FROM categories WHERE lower(name) = lower(?) AND id != ?", (name, cid))
    if dupe:
        raise ValidationError("این نام کتگوری قبلاً استفاده شده.")
    execute("UPDATE categories SET name = ? WHERE id = ?", (name, cid))
    return jsonify(_cat_public(query_one("SELECT * FROM categories WHERE id = ?", (cid,))))


@bp.delete("/<cid>")
@require_admin
def delete_category(cid):
    get_category_or_404(cid)
    in_use = query_one("SELECT COUNT(*) AS c FROM transactions WHERE category_id = ?", (cid,))["c"]
    if in_use > 0:
        raise ValidationError(
            f"این کتگوری در {in_use} تراکنش استفاده شده و قابل حذف نیست. "
            "برای حذف، ابتدا تراکنش‌های آن را به کتگوری دیگری منتقل کنید."
        )
    in_use_wd = query_one("SELECT COUNT(*) AS c FROM withdrawals WHERE category_id = ?", (cid,))["c"]
    if in_use_wd > 0:
        raise ValidationError(f"این کتگوری در {in_use_wd} برداشت استفاده شده و قابل حذف نیست.")
    if query_one("SELECT COUNT(*) AS c FROM categories")["c"] <= 1:
        raise ValidationError("حداقل یک کتگوری باید باقی بماند.")
    # ladders rows for this category cascade-delete automatically (see schema.sql).
    execute("DELETE FROM categories WHERE id = ?", (cid,))
    return jsonify({"ok": True})
