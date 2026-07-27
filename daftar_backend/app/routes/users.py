import datetime
import json

from flask import Blueprint, g, jsonify, request

from ..db import execute, query_all, query_one
from ..errors import NotFoundError, ValidationError
from ..security import PERMISSIBLE_TABS, hash_password, require_admin
from ..utils import new_id, parse_json_list_or_none

bp = Blueprint("users", __name__)


def _user_public(row) -> dict:
    return {
        "id": row["id"], "username": row["username"], "displayName": row["display_name"],
        "role": row["role"], "allowedTabs": parse_json_list_or_none(row["allowed_tabs"]),
        "createdAt": row["created_at"],
    }


@bp.get("")
@require_admin
def list_users():
    rows = query_all("SELECT * FROM users ORDER BY created_at ASC")
    return jsonify([_user_public(r) for r in rows])


@bp.post("")
@require_admin
def create_user():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    display_name = (body.get("displayName") or "").strip() or username
    role = body.get("role") or "user"
    allowed_tabs = body.get("allowedTabs")

    if not username:
        raise ValidationError("نام کاربری لازم است.")
    if len(password) < 4:
        raise ValidationError("رمز عبور باید حداقل ۴ کاراکتر باشد.")
    if role not in ("admin", "user"):
        raise ValidationError("نقش نامعتبر است.")
    if query_one("SELECT 1 FROM users WHERE lower(username) = lower(?)", (username,)):
        raise ValidationError("این نام کاربری قبلاً استفاده شده.")

    allowed_json = None
    if role != "admin":
        clean_tabs = [t for t in (allowed_tabs or PERMISSIBLE_TABS) if t in PERMISSIBLE_TABS]
        allowed_json = json.dumps(clean_tabs)

    uid_ = new_id()
    execute(
        "INSERT INTO users (id, username, password_hash, display_name, role, allowed_tabs, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (uid_, username, hash_password(password), display_name, role, allowed_json, datetime.date.today().isoformat()),
    )
    return jsonify(_user_public(query_one("SELECT * FROM users WHERE id = ?", (uid_,)))), 201


def get_user_or_404(uid_: str):
    row = query_one("SELECT * FROM users WHERE id = ?", (uid_,))
    if row is None:
        raise NotFoundError("کاربر یافت نشد.")
    return row


@bp.put("/<uid_>")
@require_admin
def update_user(uid_):
    user = get_user_or_404(uid_)
    body = request.get_json(silent=True) or {}
    display_name = (body.get("displayName") or user["display_name"]).strip()
    role = body.get("role") or user["role"]
    password = body.get("password")
    allowed_tabs = body.get("allowedTabs")

    if role not in ("admin", "user"):
        raise ValidationError("نقش نامعتبر است.")
    # Never allow demoting/deleting the last remaining admin — same guard as the frontend.
    if user["role"] == "admin" and role != "admin":
        admin_count = query_one("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'")["c"]
        if admin_count <= 1:
            raise ValidationError("حداقل یک مدیر باید در سامانه باقی بماند.")

    allowed_json = user["allowed_tabs"]
    if role != "admin":
        clean_tabs = [t for t in (allowed_tabs if allowed_tabs is not None else parse_json_list_or_none(user["allowed_tabs"]) or PERMISSIBLE_TABS) if t in PERMISSIBLE_TABS]
        allowed_json = json.dumps(clean_tabs)
    else:
        allowed_json = None

    if password:
        if len(password) < 4:
            raise ValidationError("رمز عبور باید حداقل ۴ کاراکتر باشد.")
        execute(
            "UPDATE users SET display_name=?, role=?, allowed_tabs=?, password_hash=? WHERE id=?",
            (display_name, role, allowed_json, hash_password(password), uid_),
        )
    else:
        execute(
            "UPDATE users SET display_name=?, role=?, allowed_tabs=? WHERE id=?",
            (display_name, role, allowed_json, uid_),
        )
    return jsonify(_user_public(query_one("SELECT * FROM users WHERE id = ?", (uid_,))))


@bp.delete("/<uid_>")
@require_admin
def delete_user(uid_):
    user = get_user_or_404(uid_)
    if g.user["id"] == uid_:
        raise ValidationError("نمی‌توانید حساب خودتان را در همین لحظه حذف کنید.")
    if user["role"] == "admin":
        admin_count = query_one("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'")["c"]
        if admin_count <= 1:
            raise ValidationError("حداقل یک مدیر باید در سامانه باقی بماند.")
    execute("DELETE FROM users WHERE id = ?", (uid_,))
    return jsonify({"ok": True})
