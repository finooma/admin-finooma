import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app


def make_client():
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.remove(path)  # let init_db create it fresh
    app = create_app({"DATABASE_PATH": path, "TESTING": True})
    return app.test_client(), path


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_full_flow():
    client, db_path = make_client()
    try:
        # 1. bootstrap first admin
        r = client.post("/api/auth/register", json={"username": "admin", "password": "pass1234", "displayName": "مدیر"})
        assert r.status_code == 201, r.get_json()
        token = r.get_json()["token"]
        h = auth_headers(token)

        # second register attempt should now be rejected
        r2 = client.post("/api/auth/register", json={"username": "someone", "password": "xxxx"})
        assert r2.status_code == 400

        # 2. login
        r = client.post("/api/auth/login", json={"username": "admin", "password": "pass1234"})
        assert r.status_code == 200
        assert r.get_json()["user"]["role"] == "admin"

        # 3. create portfolio
        r = client.post("/api/portfolios", json={"name": "سبد اصلی"}, headers=h)
        assert r.status_code == 201, r.get_json()
        pid = r.get_json()["id"]

        # 4. buy transaction
        r = client.post(f"/api/portfolios/{pid}/transactions", json={
            "type": "buy", "date": "1404/01/01", "asset": "BTC", "category": "کریپتو",
            "qty": 1, "price": 1000, "amount": 1000,
        }, headers=h)
        assert r.status_code == 201, r.get_json()

        # 5. set day price
        r = client.put("/api/prices/BTC", json={"price": 2000}, headers=h)
        assert r.status_code == 200

        # 6. holdings should reflect unrealized gain
        r = client.get(f"/api/portfolios/{pid}/holdings", headers=h)
        assert r.status_code == 200
        holdings = r.get_json()
        assert len(holdings) == 1
        assert holdings[0]["unrealized"] == 1000

        # 7. selling more than owned should be rejected
        r = client.post(f"/api/portfolios/{pid}/transactions", json={
            "type": "sell", "date": "1404/02/01", "asset": "BTC", "category": "کریپتو",
            "qty": 5, "price": 2000, "amount": 10000,
        }, headers=h)
        assert r.status_code == 400

        # 8. ladders default correctly for a known category
        r = client.get(f"/api/portfolios/{pid}/ladders/کریپتو", headers=h)
        assert r.status_code == 200
        levels = r.get_json()
        assert levels[0]["t"] == 70

        # 9. secure-profit: since profitPct (100%) exceeds rung 0's threshold (70%), this should work
        r = client.post(f"/api/portfolios/{pid}/secure-profit", json={
            "category": "کریپتو", "levelIdx": 0, "asset": "BTC", "date": "1404/03/01",
            "price": 2000, "qty": 0.25, "amount": 500,
        }, headers=h)
        assert r.status_code == 201, r.get_json()

        # 10. withdrawal should now show up, linked to the sell
        r = client.get(f"/api/portfolios/{pid}/withdrawals", headers=h)
        wds = r.get_json()
        assert len(wds) == 1
        assert wds[0]["level"] == 0
        assert wds[0]["sourceTxnId"]

        # 11. deleting the linked sell transaction should also delete the withdrawal
        sell_txn_id = wds[0]["sourceTxnId"]
        r = client.delete(f"/api/transactions/{sell_txn_id}", headers=h)
        assert r.status_code == 200
        assert r.get_json()["unlinkedWithdrawals"] == 1
        r = client.get(f"/api/portfolios/{pid}/withdrawals", headers=h)
        assert r.get_json() == []

        # 12. non-admin can't create a transaction
        r = client.post("/api/users", json={
            "username": "viewer", "password": "abcd1234", "role": "user", "allowedTabs": ["holdings"],
        }, headers=h)
        assert r.status_code == 201
        r = client.post("/api/auth/login", json={"username": "viewer", "password": "abcd1234"})
        viewer_h = auth_headers(r.get_json()["token"])
        r = client.post(f"/api/portfolios/{pid}/transactions", json={
            "type": "buy", "date": "1404/01/01", "asset": "ETH", "category": "کریپتو", "qty": 1, "price": 1, "amount": 1,
        }, headers=viewer_h)
        assert r.status_code == 403

        # 13. viewer can still read holdings (allowed tab)
        r = client.get(f"/api/portfolios/{pid}/holdings", headers=viewer_h)
        assert r.status_code == 200

        # 14. viewer cannot read ladders (not in allowedTabs)
        r = client.get(f"/api/portfolios/{pid}/ladders/کریپتو", headers=viewer_h)
        assert r.status_code == 403

        print("ALL API FLOW ASSERTIONS PASSED")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    test_full_flow()
