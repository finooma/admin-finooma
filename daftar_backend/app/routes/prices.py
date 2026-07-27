import datetime

from flask import Blueprint, jsonify, request

from ..db import execute, query_all
from ..errors import ValidationError
from ..security import require_admin, require_tab

bp = Blueprint("prices", __name__)


@bp.get("")
@require_tab("holdings")
def list_prices():
    rows = query_all("SELECT * FROM prices")
    return jsonify({r["asset"]: {"price": r["price"], "updatedAt": r["updated_at"]} for r in rows})


@bp.put("/<asset>")
@require_admin
def set_price(asset):
    body = request.get_json(silent=True) or {}
    price = float(body.get("price") or 0)
    if price < 0:
        raise ValidationError("قیمت نمی‌تواند منفی باشد.")
    updated_at = body.get("updatedAt") or datetime.date.today().isoformat()
    execute(
        "INSERT INTO prices (asset, price, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(asset) DO UPDATE SET price = excluded.price, updated_at = excluded.updated_at",
        (asset, price, updated_at),
    )
    return jsonify({"asset": asset, "price": price, "updatedAt": updated_at})
