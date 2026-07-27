from flask import Blueprint, jsonify, request

from ..business import category_agg, compute_holdings_for_portfolio, jalali_sort_key
from ..db import query_all
from ..routes.portfolios import get_portfolio_or_404
from ..security import require_tab
from ..utils import normalize_jalali

bp = Blueprint("holdings", __name__)


def _txns_for_portfolio(pid: str) -> list[dict]:
    rows = query_all("SELECT * FROM transactions WHERE portfolio_id = ?", (pid,))
    return [dict(r) for r in rows]


def _prices_dict() -> dict[str, float]:
    rows = query_all("SELECT asset, price FROM prices")
    return {r["asset"]: r["price"] for r in rows}


@bp.get("/<pid>/holdings")
@require_tab("holdings")
def get_holdings(pid):
    get_portfolio_or_404(pid)
    as_of_raw = request.args.get("as_of")
    as_of = normalize_jalali(as_of_raw) if as_of_raw else None
    if as_of_raw and not as_of:
        from ..errors import ValidationError

        raise ValidationError("فرمت تاریخ نما (as_of) درست نیست.")

    result = compute_holdings_for_portfolio(_txns_for_portfolio(pid), _prices_dict(), as_of)
    holdings = result["holdings"]
    for h in holdings:
        h["portfolioId"] = pid
    holdings.sort(key=lambda h: h["value"], reverse=True)
    return jsonify(holdings)


@bp.get("/<pid>/closed")
@require_tab("sold")
def get_closed(pid):
    get_portfolio_or_404(pid)
    result = compute_holdings_for_portfolio(_txns_for_portfolio(pid), _prices_dict())
    closed = result["closed"]
    for c in closed:
        c["portfolioId"] = pid
    closed.sort(key=lambda c: jalali_sort_key(c["lastSell"]), reverse=True)
    return jsonify(closed)


@bp.get("/<pid>/category-summary")
@require_tab("ladders")
def category_summary(pid):
    get_portfolio_or_404(pid)
    result = compute_holdings_for_portfolio(_txns_for_portfolio(pid), _prices_dict())
    agg = category_agg(result["holdings"], result["closed"])
    return jsonify(agg)
