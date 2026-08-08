import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.business import (
    compute_holdings, category_agg, compute_asset_txn_realized,
    ladder_levels_with_defaults, ladder_rung_calc, DEFAULT_LADDERS,
    txn_cash_impact, compute_account_balance,
)


def txn(id, type, date, asset, category_id="crypto", qty=0, price=0, amount=0, fee=0, ts=0, account_id=None):
    return {"id": id, "type": type, "date": date, "asset": asset, "category_id": category_id,
            "qty": qty, "price": price, "amount": amount, "fee": fee, "location": "", "ts": ts,
            "account_id": account_id}


def test_weighted_average_cost_on_partial_sell():
    txns = [
        txn("1", "buy", "1404/01/01", "BTC", qty=1, price=100, amount=100),
        txn("2", "buy", "1404/02/01", "BTC", qty=1, price=200, amount=200),
        # avg cost now 150/unit, qty=2
        txn("3", "sell", "1404/03/01", "BTC", qty=1, price=300, amount=300),
    ]
    result = compute_holdings(txns, prices={"BTC": 400})
    h = result["holdings"][0]
    assert h["qty"] == 1
    assert h["avgCost"] == 150
    assert h["costBasis"] == 150
    assert h["realized"] == 300 - 150  # realized P/L from the sell
    assert h["value"] == 400  # 1 unit * day price
    assert h["unrealized"] == 400 - 150


def test_fee_increases_buy_cost_and_reduces_sell_proceeds():
    txns = [
        txn("1", "buy", "1404/01/01", "BTC", qty=1, price=100, amount=100, fee=5),
        # cost basis is 105 (100 + 5 fee), not 100
    ]
    result = compute_holdings(txns, prices={"BTC": 200})
    h = result["holdings"][0]
    assert h["costBasis"] == 105
    assert h["avgCost"] == 105

    txns2 = txns + [
        txn("2", "sell", "1404/02/01", "BTC", qty=1, price=200, amount=200, fee=10),
        # net proceeds are 190 (200 - 10 fee); realized = 190 - 105 = 85
    ]
    result2 = compute_holdings(txns2, prices={})
    assert result2["closed"][0]["profit"] == 190 - 105


def test_full_exit_creates_closed_lot_and_resets():
    txns = [
        txn("1", "buy", "1404/01/01", "ETH", qty=2, price=100, amount=200),
        txn("2", "sell", "1404/02/01", "ETH", qty=2, price=150, amount=300),
        txn("3", "buy", "1404/03/01", "ETH", qty=1, price=500, amount=500),
    ]
    result = compute_holdings(txns, prices={"ETH": 500})
    assert len(result["closed"]) == 1
    closed = result["closed"][0]
    assert closed["profit"] == 300 - 200
    # re-buy after full exit starts a fresh lot, unaffected by the earlier closed lot
    h = result["holdings"][0]
    assert h["qty"] == 1
    assert h["costBasis"] == 500


def test_dividend_after_close_attributed_to_closed_lot():
    txns = [
        txn("1", "buy", "1404/01/01", "FUND", qty=10, price=10, amount=100),
        txn("2", "sell", "1404/02/01", "FUND", qty=10, price=12, amount=120),
        txn("3", "dividend", "1404/02/15", "FUND", amount=5),
    ]
    result = compute_holdings(txns, prices={})
    assert result["holdings"] == []
    assert result["closed"][0]["profit"] == (120 - 100) + 5


def test_sell_never_oversells_defensive_clamp():
    txns = [
        txn("1", "buy", "1404/01/01", "X", qty=1, price=100, amount=100),
        txn("2", "sell", "1404/02/01", "X", qty=5, price=100, amount=500),  # more than owned
    ]
    result = compute_holdings(txns, prices={})
    assert result["holdings"] == []
    assert result["closed"][0]["invested"] == 100


def test_category_agg_sums_across_assets_and_closed_lots():
    holdings = [
        {"categoryId": "gold", "costBasis": 100, "value": 150, "unrealized": 50, "realized": 0},
        {"categoryId": "gold", "costBasis": 200, "value": 180, "unrealized": -20, "realized": 10},
    ]
    closed = [{"categoryId": "gold", "profit": 40}]
    agg = category_agg(holdings, closed)
    g = agg["gold"]
    assert g["investment"] == 300
    assert g["value"] == 330
    assert g["unrealized"] == 30
    assert g["realized"] == 10 + 40
    assert round(g["profitPct"], 4) == round(30 / 300 * 100, 4)


def test_ladder_defaults_fall_back_correctly():
    assert ladder_levels_with_defaults("طلا", None) == DEFAULT_LADDERS["طلا"]
    assert ladder_levels_with_defaults("یک کتگوری عجیب", None) == DEFAULT_LADDERS["سایر"]
    custom = [{"t": 10, "w": 20}]
    assert ladder_levels_with_defaults("طلا", custom) == custom


def test_ladder_rung_calc_matches_frontend_formula():
    a = {"investment": 1000, "profitPct": 80}
    lv = {"t": 70, "w": 50}
    r = ladder_rung_calc(a, lv)
    assert r["profitAtThreshold"] == 700
    assert r["withdrawAmt"] == 350
    assert r["achieved"] is True
    assert r["progress"] == 100  # capped at 100 even though 80/70*100 > 100


def test_compute_asset_txn_realized_sums_to_holdings_realized():
    txns = [
        txn("1", "buy", "1404/01/01", "BTC", qty=2, price=100, amount=200),
        txn("2", "sell", "1404/02/01", "BTC", qty=1, price=150, amount=150),
        txn("3", "sell", "1404/03/01", "BTC", qty=1, price=200, amount=200),
    ]
    per_txn = compute_asset_txn_realized(txns)
    holdings_result = compute_holdings(txns, prices={})
    total_realized = sum(c["profit"] for c in holdings_result["closed"])
    assert round(sum(per_txn.values()), 6) == round(total_realized, 6)


def test_txn_cash_impact_buy_sell_dividend():
    assert txn_cash_impact({"type": "buy", "amount": 100, "fee": 5}) == -105
    assert txn_cash_impact({"type": "sell", "amount": 100, "fee": 5}) == 95
    assert txn_cash_impact({"type": "dividend", "amount": 20, "fee": 0}) == 20


def test_compute_account_balance_combines_opening_movements_and_transactions():
    movements = [
        {"type": "deposit", "amount": 1000},
        {"type": "withdraw", "amount": 200},
    ]
    txns_for_account = [
        {"type": "buy", "amount": 300, "fee": 3},   # -303
        {"type": "sell", "amount": 150, "fee": 2},  # +148
    ]
    balance = compute_account_balance(500, movements, txns_for_account)
    # 500 (opening) + 1000 - 200 - 303 + 148
    assert balance == 500 + 1000 - 200 - 303 + 148
