"""Pure, side-effect-free business logic — a faithful Python port of the calculation
functions in daftar-darayi_28.html (computeHoldings, categoryAgg, computeAssetTxnRealized,
ensurePortfolioLadders's defaults, etc).

Deliberately has zero imports from Flask or sqlite: everything here takes plain
dicts/lists and returns plain dicts/lists, so it can be unit-tested in isolation
(see tests/test_business.py) and re-used unchanged if the storage layer ever changes.
"""
from __future__ import annotations

import re
from typing import Optional

EPS = 1e-9
EPS_SMALL = 1e-6

DEFAULT_LADDERS = {
    "کریپتو": [{"t": 70, "w": 50}, {"t": 110, "w": 80}, {"t": 200, "w": 90}],
    "طلا": [{"t": 80, "w": 50}, {"t": 120, "w": 80}, {"t": 180, "w": 90}],
    "بورس": [{"t": 50, "w": 50}, {"t": 100, "w": 80}, {"t": 180, "w": 90}],
    "درآمد ثابت": [{"t": 20, "w": 50}, {"t": 40, "w": 80}, {"t": 60, "w": 90}],
    "ارز": [{"t": 30, "w": 50}, {"t": 60, "w": 80}, {"t": 100, "w": 90}],
    "نقره": [{"t": 50, "w": 50}, {"t": 100, "w": 80}, {"t": 150, "w": 90}],
    "سایر": [{"t": 50, "w": 50}, {"t": 100, "w": 80}, {"t": 150, "w": 90}],
}
BASE_CATEGORIES = list(DEFAULT_LADDERS.keys())

_JALALI_RE = re.compile(r"^(\d{4})/(\d{2})/(\d{2})$")


def jalali_sort_key(date_str: Optional[str]) -> int:
    """Zero-padded 'YYYY/MM/DD' sorts correctly as an integer, exactly like the frontend."""
    if not date_str:
        return 0
    m = _JALALI_RE.match(date_str)
    if not m:
        return 0
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return y * 10000 + mo * 100 + d


def pl_class(n: float) -> str:
    if n > EPS_SMALL:
        return "pos"
    if n < -EPS_SMALL:
        return "neg"
    return ""


def compute_holdings(txns: list[dict], prices: dict[str, float]) -> dict:
    """Replays a chronological ledger of buy/sell/dividend transactions for ONE portfolio
    (never mix portfolios here — see compute_holdings_for_portfolio) using weighted-average
    cost. Returns {"holdings": [...open positions...], "closed": [...fully exited lots...]}.

    This mirrors computeHoldings() in the frontend line for line, including the edge cases:
    - a sell is clamped to available qty (defensive; real prevention happens at write time)
    - realized P/L on a partial sell is proportional to the sold quantity
    - closing a position to exactly zero qty snapshots it as a "closed lot" and resets the lot
    - a dividend paid after a position is already closed is attributed back to that closed lot
    """
    assets: dict[str, dict] = {}
    closed_list: list[dict] = []
    last_closed_for_asset: dict[str, dict] = {}

    sorted_txns = sorted(txns, key=lambda t: (jalali_sort_key(t["date"]), t.get("ts", 0)))

    for t in sorted_txns:
        name = t["asset"]
        a = assets.setdefault(
            name,
            {
                "qty": 0.0, "avgCost": 0.0, "costBasis": 0.0, "realizedPL": 0.0, "dividend": 0.0,
                "category": t.get("category"), "location": t.get("location") or "",
                "firstBuy": None, "lotInvested": 0.0, "lotReceived": 0.0,
            },
        )
        if t.get("category"):
            a["category"] = t["category"]
        if t.get("location"):
            a["location"] = t["location"]

        if t["type"] == "buy":
            if a["qty"] <= EPS:
                a["firstBuy"] = t["date"]
                a["lotInvested"] = 0.0
                a["lotReceived"] = 0.0
            a["costBasis"] += t["amount"]
            a["qty"] += t["qty"]
            a["avgCost"] = a["costBasis"] / a["qty"] if a["qty"] > EPS else 0.0
            a["lotInvested"] += t["amount"]

        elif t["type"] == "sell":
            sell_qty = min(t["qty"], a["qty"])
            proportional_cost = sell_qty * a["avgCost"]
            proportional_proceeds = t["amount"] * (sell_qty / t["qty"]) if t["qty"] > EPS else 0.0
            a["realizedPL"] += proportional_proceeds - proportional_cost
            a["lotReceived"] += proportional_proceeds
            a["qty"] -= sell_qty
            if a["qty"] < EPS_SMALL:
                a["qty"] = 0.0
            a["costBasis"] = a["qty"] * a["avgCost"]
            if a["qty"] == 0:
                rec = {
                    "asset": name, "category": a["category"],
                    "profit": a["realizedPL"] + a["dividend"],
                    "firstBuy": a["firstBuy"], "lastSell": t["date"],
                    "invested": a["lotInvested"], "received": a["lotReceived"],
                }
                closed_list.append(rec)
                last_closed_for_asset[name] = rec
                a["avgCost"] = 0.0
                a["realizedPL"] = 0.0
                a["dividend"] = 0.0
                a["firstBuy"] = None
                a["lotInvested"] = 0.0
                a["lotReceived"] = 0.0

        elif t["type"] == "dividend":
            if a["qty"] > EPS:
                a["dividend"] += t["amount"]
            else:
                lc = last_closed_for_asset.get(name)
                if lc:
                    lc["profit"] += t["amount"]

    holdings = []
    for name, a in assets.items():
        if a["qty"] > EPS:
            price = prices.get(name, 0) or 0
            has_price = price > EPS
            value = a["qty"] * price if has_price else a["costBasis"]
            unrealized = (value - a["costBasis"]) if has_price else 0.0
            unrealized_pct = (unrealized / a["costBasis"] * 100) if (has_price and a["costBasis"] > EPS_SMALL) else 0.0
            realized = a["realizedPL"] + a["dividend"]
            holdings.append({
                "name": name, "category": a["category"], "location": a["location"],
                "qty": a["qty"], "avgCost": a["avgCost"], "costBasis": a["costBasis"],
                "price": price, "hasPrice": has_price, "value": value,
                "unrealized": unrealized, "unrealizedPct": unrealized_pct,
                "realized": realized, "totalPL": unrealized + realized, "firstBuy": a["firstBuy"],
            })

    holdings.sort(key=lambda h: h["value"], reverse=True)
    closed_list.sort(key=lambda c: jalali_sort_key(c["lastSell"]), reverse=True)
    return {"holdings": holdings, "closed": closed_list}


def compute_holdings_for_portfolio(
    txns_for_portfolio: list[dict], prices: dict[str, float], as_of_date: Optional[str] = None
) -> dict:
    txns = txns_for_portfolio
    if as_of_date:
        cutoff = jalali_sort_key(as_of_date)
        txns = [t for t in txns if jalali_sort_key(t["date"]) <= cutoff]
    return compute_holdings(txns, prices)


def compute_asset_txn_realized(txns_for_asset_and_portfolio: list[dict]) -> dict[str, float]:
    """Per-transaction realized P/L for one asset within one portfolio, keyed by txn id —
    same weighted-average logic as compute_holdings, but attributed per sell instead of summed.
    Summing every value in the returned dict reproduces that asset's aggregate realized P/L."""
    result: dict[str, float] = {}
    sorted_txns = sorted(txns_for_asset_and_portfolio, key=lambda t: (jalali_sort_key(t["date"]), t.get("ts", 0)))
    qty = 0.0
    avg_cost = 0.0
    cost_basis = 0.0
    last_closed_txn_id = None

    for t in sorted_txns:
        if t["type"] == "buy":
            cost_basis += t["amount"]
            qty += t["qty"]
            avg_cost = cost_basis / qty if qty > EPS else 0.0
            last_closed_txn_id = None
        elif t["type"] == "sell":
            sell_qty = min(t["qty"], qty)
            proportional_cost = sell_qty * avg_cost
            proportional_proceeds = t["amount"] * (sell_qty / t["qty"]) if t["qty"] > EPS else 0.0
            result[t["id"]] = proportional_proceeds - proportional_cost
            qty -= sell_qty
            if qty < EPS_SMALL:
                qty = 0.0
            cost_basis = qty * avg_cost
            if qty == 0:
                avg_cost = 0.0
                last_closed_txn_id = t["id"]
            else:
                last_closed_txn_id = None
        elif t["type"] == "dividend":
            if qty > EPS:
                result[t["id"]] = t["amount"]
            elif last_closed_txn_id:
                result[last_closed_txn_id] = result.get(last_closed_txn_id, 0.0) + t["amount"]
                result[t["id"]] = 0.0
            else:
                result[t["id"]] = t["amount"]

    return result


def category_agg(holdings: list[dict], closed: Optional[list[dict]] = None) -> dict[str, dict]:
    closed = closed or []
    agg: dict[str, dict] = {}

    def ensure(cat):
        return agg.setdefault(cat, {"investment": 0.0, "value": 0.0, "unrealized": 0.0, "realized": 0.0})

    for h in holdings:
        c = ensure(h["category"])
        c["investment"] += h["costBasis"]
        c["value"] += h["value"]
        c["unrealized"] += h["unrealized"]
        c["realized"] += h["realized"]

    for c in closed:
        ensure(c["category"])["realized"] += c["profit"]

    for c in agg.values():
        c["overall"] = c["unrealized"] + c["realized"]
        c["profit"] = c["unrealized"]  # kept for the profit-ladder tab, which plans off unrealized gains
        c["profitPct"] = (c["unrealized"] / c["investment"] * 100) if c["investment"] > EPS_SMALL else 0.0

    return agg


def current_qty_for_asset(name: str, txns_for_portfolio_excl: list[dict], prices: dict[str, float]) -> float:
    """txns_for_portfolio_excl should already be filtered to the right portfolio and, if
    editing/replacing a transaction, already exclude that transaction's id."""
    result = compute_holdings(txns_for_portfolio_excl, prices)
    for h in result["holdings"]:
        if h["name"] == name:
            return h["qty"]
    return 0.0


def ladder_levels_with_defaults(cat: str, stored_levels: Optional[list[dict]]) -> list[dict]:
    """Equivalent of ensurePortfolioLadders()[cat] in the frontend: use stored rungs if present,
    otherwise fall back to that category's defaults (or the catch-all 'سایر' defaults for an
    unknown/custom category)."""
    if stored_levels:
        return stored_levels
    return [dict(lv) for lv in DEFAULT_LADDERS.get(cat, DEFAULT_LADDERS["سایر"])]


def ladder_rung_calc(a: dict, lv: dict) -> dict:
    """Given a category's aggregate {investment, profitPct, ...} and one ladder rung {t, w},
    returns the numbers rendered per-row in the ladders tab (threshold profit, suggested
    withdrawal, target/remaining capital, achieved flag, progress percent)."""
    profit_at_threshold = a["investment"] * lv["t"] / 100
    withdraw_amt = profit_at_threshold * lv["w"] / 100
    target_value = a["investment"] + profit_at_threshold
    remaining = target_value - withdraw_amt
    achieved = a["profitPct"] >= lv["t"] and a["investment"] > EPS_SMALL
    progress = min(100.0, max(0.0, a["profitPct"] / lv["t"] * 100)) if a["investment"] > EPS_SMALL else 0.0
    return {
        "profitAtThreshold": profit_at_threshold, "withdrawAmt": withdraw_amt,
        "targetValue": target_value, "remaining": remaining,
        "achieved": achieved, "progress": progress,
    }
