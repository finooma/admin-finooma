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

        # 4. categories are pre-seeded (7 base categories); grab کریپتو's id
        r = client.get("/api/categories", headers=h)
        cats = r.get_json()
        assert len(cats) == 7
        crypto_id = next(c["id"] for c in cats if c["name"] == "کریپتو")

        # 4b. category management: create, rename, and block-deleting an in-use one
        r = client.post("/api/categories", json={"name": "کتگوری تست"}, headers=h)
        assert r.status_code == 201
        test_cat_id = r.get_json()["id"]
        r = client.put(f"/api/categories/{test_cat_id}", json={"name": "کتگوری تست ۲"}, headers=h)
        assert r.status_code == 200 and r.get_json()["name"] == "کتگوری تست ۲"
        r = client.delete(f"/api/categories/{test_cat_id}", headers=h)
        assert r.status_code == 200  # unused -> deletable

        # 5. create a cash account for this portfolio, deposit into it
        r = client.post(f"/api/accounts", json={"name": "نقد تومانی", "openingBalance": 0}, headers=h)
        assert r.status_code == 201, r.get_json()
        acc_id = r.get_json()["id"]
        assert r.get_json()["balance"] == 0

        r = client.post(f"/api/accounts/{acc_id}/deposit", json={"date": "1404/01/01", "amount": 10000, "note": "واریز اولیه"}, headers=h)
        assert r.status_code == 201
        assert r.get_json()["balance"] == 10000

        # 6. buy transaction WITH a fee, paid from that account — cash should drop by amount+fee
        r = client.post(f"/api/portfolios/{pid}/transactions", json={
            "type": "buy", "date": "1404/01/02", "asset": "BTC", "categoryId": crypto_id, "accountId": acc_id,
            "qty": 1, "price": 1000, "amount": 1000, "fee": 20,
        }, headers=h)
        assert r.status_code == 201, r.get_json()
        assert r.get_json()["fee"] == 20
        assert r.get_json()["total"] == 1020  # amount + fee on a buy

        r = client.get(f"/api/accounts/{acc_id}/movements", headers=h)  # sanity: account still resolvable
        assert r.status_code == 200
        r = client.get(f"/api/accounts", headers=h)
        acc_after_buy = next(a for a in r.get_json() if a["id"] == acc_id)
        assert acc_after_buy["balance"] == 10000 - 1020

        # 7. holdings should reflect fee-inclusive cost basis
        r = client.put("/api/prices/BTC", json={"price": 2000}, headers=h)
        assert r.status_code == 200
        r = client.get(f"/api/portfolios/{pid}/holdings", headers=h)
        holdings = r.get_json()
        assert len(holdings) == 1
        assert holdings[0]["costBasis"] == 1020
        assert holdings[0]["categoryId"] == crypto_id

        # 8. selling more than owned should be rejected
        r = client.post(f"/api/portfolios/{pid}/transactions", json={
            "type": "sell", "date": "1404/02/01", "asset": "BTC", "categoryId": crypto_id,
            "qty": 5, "price": 2000, "amount": 10000,
        }, headers=h)
        assert r.status_code == 400

        # 9. ladders default correctly for a known category (by id now)
        r = client.get(f"/api/portfolios/{pid}/ladders/{crypto_id}", headers=h)
        assert r.status_code == 200
        levels = r.get_json()
        assert levels[0]["t"] == 70

        # 10. secure-profit: sell with a fee, into the same account — net proceeds credited
        r = client.post(f"/api/portfolios/{pid}/secure-profit", json={
            "categoryId": crypto_id, "levelIdx": 0, "asset": "BTC", "date": "1404/03/01",
            "price": 2000, "qty": 0.25, "amount": 500, "fee": 10, "accountId": acc_id,
        }, headers=h)
        assert r.status_code == 201, r.get_json()
        assert r.get_json()["netProceeds"] == 490

        r = client.get(f"/api/accounts", headers=h)
        acc_after_sell = next(a for a in r.get_json() if a["id"] == acc_id)
        assert acc_after_sell["balance"] == (10000 - 1020) + 490

        # 11. withdrawal should now show up, linked to the sell, amount = net proceeds
        r = client.get(f"/api/portfolios/{pid}/withdrawals", headers=h)
        wds = r.get_json()
        assert len(wds) == 1
        assert wds[0]["level"] == 0
        assert wds[0]["amount"] == 490
        assert wds[0]["sourceTxnId"]

        # 12. deleting the linked sell transaction should also delete the withdrawal
        sell_txn_id = wds[0]["sourceTxnId"]
        r = client.delete(f"/api/transactions/{sell_txn_id}", headers=h)
        assert r.status_code == 200
        assert r.get_json()["unlinkedWithdrawals"] == 1
        r = client.get(f"/api/portfolios/{pid}/withdrawals", headers=h)
        assert r.get_json() == []

        # 13. a second account + transfer between accounts
        r = client.post(f"/api/accounts", json={"name": "نقد دلاری", "openingBalance": 0}, headers=h)
        acc2_id = r.get_json()["id"]
        r = client.post(f"/api/accounts/transfer", json={
            "fromAccountId": acc_id, "toAccountId": acc2_id, "date": "1404/03/02", "amount": 1000, "note": "انتقال",
        }, headers=h)
        assert r.status_code == 201, r.get_json()
        assert r.get_json()["to"]["balance"] == 1000

        # 14. can't delete a category that's in use
        r = client.delete(f"/api/categories/{crypto_id}", headers=h)
        assert r.status_code == 400

        # 15. non-admin can't create a transaction
        r = client.post("/api/users", json={
            "username": "viewer", "password": "abcd1234", "role": "user", "allowedTabs": ["holdings"],
        }, headers=h)
        assert r.status_code == 201
        r = client.post("/api/auth/login", json={"username": "viewer", "password": "abcd1234"})
        viewer_h = auth_headers(r.get_json()["token"])
        r = client.post(f"/api/portfolios/{pid}/transactions", json={
            "type": "buy", "date": "1404/01/01", "asset": "ETH", "categoryId": crypto_id, "qty": 1, "price": 1, "amount": 1,
        }, headers=viewer_h)
        assert r.status_code == 403

        # 16. viewer can still read holdings (allowed tab)
        r = client.get(f"/api/portfolios/{pid}/holdings", headers=viewer_h)
        assert r.status_code == 200

        # 17. viewer cannot read ladders (not in allowedTabs)
        r = client.get(f"/api/portfolios/{pid}/ladders/{crypto_id}", headers=viewer_h)
        assert r.status_code == 403

        print("ALL API FLOW ASSERTIONS PASSED")
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    test_full_flow()
