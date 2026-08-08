from flask import Blueprint, jsonify, request

from ..business import BASE_CATEGORIES, ladder_levels_with_defaults
from ..db import execute, query_all, query_one
from ..errors import ValidationError, NotFoundError
from ..routes.portfolios import get_portfolio_or_404
from ..security import require_admin, require_tab

bp = Blueprint("ladders", __name__)


def _category_name(cid: str) -> str:
    row = query_one("SELECT name FROM categories WHERE id = ?", (cid,))
    return row["name"] if row else "سایر"


def get_category_or_404(cid: str):
    row = query_one("SELECT * FROM categories WHERE id = ?", (cid,))
    if row is None:
        raise NotFoundError("کتگوری یافت نشد.")
    return row


def _stored_levels(pid: str, category_id: str) -> list[dict] | None:
    rows = query_all(
        "SELECT idx, threshold_pct, withdraw_pct FROM ladders WHERE portfolio_id = ? AND category_id = ? ORDER BY idx",
        (pid, category_id),
    )
    if not rows:
        return None
    return [{"t": r["threshold_pct"], "w": r["withdraw_pct"]} for r in rows]


@bp.get("/<pid>/ladders")
@require_tab("ladders")
def get_all_ladders(pid):
    """Returns every category's ladder for this portfolio, keyed by category_id — every base
    category plus any custom category actually used by a transaction in this portfolio."""
    get_portfolio_or_404(pid)
    used_ids = {r["category_id"] for r in query_all(
        "SELECT DISTINCT category_id FROM transactions WHERE portfolio_id = ?", (pid,)
    )}
    base_ids = {r["id"] for r in query_all(
        "SELECT id FROM categories WHERE name IN ({})".format(",".join("?" * len(BASE_CATEGORIES))),
        tuple(BASE_CATEGORIES),
    )}
    all_ids = used_ids | base_ids
    out = {}
    for cid in all_ids:
        out[cid] = ladder_levels_with_defaults(_category_name(cid), _stored_levels(pid, cid))
    return jsonify(out)


@bp.get("/<pid>/ladders/<cid>")
@require_tab("ladders")
def get_ladder(pid, cid):
    get_portfolio_or_404(pid)
    get_category_or_404(cid)
    return jsonify(ladder_levels_with_defaults(_category_name(cid), _stored_levels(pid, cid)))


@bp.put("/<pid>/ladders/<cid>")
@require_admin
def set_ladder(pid, cid):
    """Body: {"levels": [{"t":70,"w":50}, {"t":110,"w":80}, {"t":200,"w":90}]} — full replace
    of this category's rungs, same as editing the threshold/withdraw-% inputs in the frontend."""
    get_portfolio_or_404(pid)
    get_category_or_404(cid)
    body = request.get_json(silent=True) or {}
    levels = body.get("levels")
    if not isinstance(levels, list) or not levels:
        raise ValidationError("لیست پله‌ها لازم است.")
    clean = []
    for lv in levels:
        t = max(0.0, float(lv.get("t", 0)))
        w = max(0.0, float(lv.get("w", 0)))
        clean.append((t, w))

    execute("DELETE FROM ladders WHERE portfolio_id = ? AND category_id = ?", (pid, cid))
    for idx, (t, w) in enumerate(clean):
        execute(
            "INSERT INTO ladders (portfolio_id, category_id, idx, threshold_pct, withdraw_pct) VALUES (?, ?, ?, ?, ?)",
            (pid, cid, idx, t, w),
        )
    return jsonify([{"t": t, "w": w} for t, w in clean])
