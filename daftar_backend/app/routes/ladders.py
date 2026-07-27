from flask import Blueprint, jsonify, request

from ..business import BASE_CATEGORIES, DEFAULT_LADDERS, ladder_levels_with_defaults
from ..db import execute, query_all
from ..errors import ValidationError
from ..routes.portfolios import get_portfolio_or_404
from ..security import require_admin, require_tab

bp = Blueprint("ladders", __name__)


def _stored_levels(pid: str, cat: str) -> list[dict] | None:
    rows = query_all(
        "SELECT idx, threshold_pct, withdraw_pct FROM ladders WHERE portfolio_id = ? AND category = ? ORDER BY idx",
        (pid, cat),
    )
    if not rows:
        return None
    return [{"t": r["threshold_pct"], "w": r["withdraw_pct"]} for r in rows]


@bp.get("/<pid>/ladders")
@require_tab("ladders")
def get_all_ladders(pid):
    """Returns every known category's ladder for this portfolio — known categories are the
    7 base ones plus any custom category actually used in a transaction, exactly like
    knownCategories() in the frontend."""
    get_portfolio_or_404(pid)
    txn_cats = {r["category"] for r in query_all(
        "SELECT DISTINCT category FROM transactions WHERE portfolio_id = ?", (pid,)
    )}
    all_cats = list(dict.fromkeys(BASE_CATEGORIES + sorted(txn_cats)))
    out = {}
    for cat in all_cats:
        out[cat] = ladder_levels_with_defaults(cat, _stored_levels(pid, cat))
    return jsonify(out)


@bp.get("/<pid>/ladders/<cat>")
@require_tab("ladders")
def get_ladder(pid, cat):
    get_portfolio_or_404(pid)
    return jsonify(ladder_levels_with_defaults(cat, _stored_levels(pid, cat)))


@bp.put("/<pid>/ladders/<cat>")
@require_admin
def set_ladder(pid, cat):
    """Body: {"levels": [{"t":70,"w":50}, {"t":110,"w":80}, {"t":200,"w":90}]} — full replace
    of this category's rungs, same as editing the threshold/withdraw-% inputs in the frontend."""
    get_portfolio_or_404(pid)
    body = request.get_json(silent=True) or {}
    levels = body.get("levels")
    if not isinstance(levels, list) or not levels:
        raise ValidationError("لیست پله‌ها لازم است.")
    clean = []
    for lv in levels:
        t = max(0.0, float(lv.get("t", 0)))
        w = max(0.0, float(lv.get("w", 0)))
        clean.append((t, w))

    execute("DELETE FROM ladders WHERE portfolio_id = ? AND category = ?", (pid, cat))
    for idx, (t, w) in enumerate(clean):
        execute(
            "INSERT INTO ladders (portfolio_id, category, idx, threshold_pct, withdraw_pct) VALUES (?, ?, ?, ?, ?)",
            (pid, cat, idx, t, w),
        )
    return jsonify([{"t": t, "w": w} for t, w in clean])
