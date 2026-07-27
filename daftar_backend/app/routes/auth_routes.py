from flask import Blueprint, g, jsonify, request

from ..db import execute, query_one
from ..errors import ValidationError, AuthError
from ..security import hash_password, verify_password, issue_token, require_auth
from ..utils import new_id, parse_json_list_or_none

bp = Blueprint("auth", __name__)


def _user_public(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "displayName": row["display_name"],
        "role": row["role"],
        "allowedTabs": parse_json_list_or_none(row["allowed_tabs"]),
        "createdAt": row["created_at"],
    }


@bp.get("/bootstrap-status")
def bootstrap_status():
    """Public (no auth) — lets the frontend decide whether to show the first-run
    'ثبت‌نام مدیر' form or the normal login form, before it has any token yet."""
    count = query_one("SELECT COUNT(*) AS c FROM users")["c"]
    return jsonify({"hasUsers": count > 0})


@bp.post("/register")
def register():
    """Bootstraps the very first account as an admin — mirrors the frontend's "ثبت‌نام مدیر"
    flow, which is only offered when USERS is empty. Once at least one user exists, further
    account creation must go through /api/users (admin-only)."""
    existing_count = query_one("SELECT COUNT(*) AS c FROM users")["c"]
    if existing_count > 0:
        raise ValidationError("سیستم قبلاً راه‌اندازی شده؛ برای ساخت کاربر جدید از بخش «کاربران» استفاده کنید.")

    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    display_name = (body.get("displayName") or "").strip() or username

    if not username:
        raise ValidationError("نام کاربری لازم است.")
    if len(password) < 4:
        raise ValidationError("رمز عبور باید حداقل ۴ کاراکتر باشد.")

    user_id = new_id()
    import datetime

    execute(
        "INSERT INTO users (id, username, password_hash, display_name, role, allowed_tabs, created_at) "
        "VALUES (?, ?, ?, ?, 'admin', NULL, ?)",
        (user_id, username, hash_password(password), display_name, datetime.date.today().isoformat()),
    )
    user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    return jsonify({"token": issue_token(user_id), "user": _user_public(user)}), 201


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""

    user = query_one("SELECT * FROM users WHERE lower(username) = lower(?)", (username,))
    if user is None or not verify_password(password, user["password_hash"]):
        raise AuthError("نام کاربری یا رمز عبور اشتباه است.")

    return jsonify({"token": issue_token(user["id"]), "user": _user_public(user)})


@bp.get("/me")
@require_auth
def me():
    return jsonify(_user_public(g.user))
