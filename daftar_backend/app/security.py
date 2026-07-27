import datetime
import functools

import jwt
from flask import current_app, g, request
from werkzeug.security import check_password_hash, generate_password_hash

from .db import query_one
from .errors import AuthError, ForbiddenError

# Tabs a non-admin user can be granted access to (same set as TAB_KEYS_PERMISSIBLE
# in the frontend). "سبدها" (portfolios) and "کاربران" (users) stay admin-only always.
PERMISSIBLE_TABS = ["dashboard", "add", "holdings", "sold", "trend", "ladders"]


def hash_password(raw: str) -> str:
    return generate_password_hash(raw)


def verify_password(raw: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, raw)


def issue_token(user_id: str) -> str:
    now = datetime.datetime.utcnow()
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + datetime.timedelta(days=current_app.config["JWT_EXPIRES_DAYS"]),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm=current_app.config["JWT_ALGORITHM"])


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=[current_app.config["JWT_ALGORITHM"]])
    except jwt.ExpiredSignatureError:
        raise AuthError("نشست شما منقضی شده؛ دوباره وارد شوید.")
    except jwt.InvalidTokenError:
        raise AuthError("توکن ورود نامعتبر است.")


def _load_user_from_request():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthError("ابتدا وارد شوید.")
    token = auth_header[len("Bearer "):].strip()
    payload = _decode_token(token)
    user = query_one("SELECT * FROM users WHERE id = ?", (payload["sub"],))
    if user is None:
        raise AuthError("حساب کاربری یافت نشد.")
    return user


def require_auth(fn):
    """Populates g.user with the authenticated user row, or raises AuthError (401)."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = _load_user_from_request()
        return fn(*args, **kwargs)

    return wrapper


def require_admin(fn):
    """Like require_auth, but additionally requires role == 'admin' (403 otherwise).
    This is the server-side equivalent of requireAdmin(...) in the frontend — except it's
    actually enforceable, since the client can no longer just skip the check."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = _load_user_from_request()
        if g.user["role"] != "admin":
            raise ForbiddenError("این عملیات فقط برای مدیر مجاز است.")
        return fn(*args, **kwargs)

    return wrapper


def require_tab(tab_key: str):
    """Decorator factory: admin always passes; a non-admin user must have tab_key in their
    allowed_tabs (NULL/absent allowed_tabs means every permissible tab, matching userAllowedTabs())."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            g.user = _load_user_from_request()
            if g.user["role"] != "admin":
                import json

                allowed = json.loads(g.user["allowed_tabs"]) if g.user["allowed_tabs"] else PERMISSIBLE_TABS
                if tab_key not in allowed:
                    raise ForbiddenError(f"شما به بخش «{tab_key}» دسترسی ندارید.")
            return fn(*args, **kwargs)

        return wrapper

    return decorator
