from flask import Flask, jsonify, send_from_directory
import os

from .config import Config
from .db import init_db, close_db
from .errors import ApiError


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    init_db(app)
    app.teardown_appcontext(close_db)

    # ---- CORS ----
    # Lets the frontend be opened from a different origin than the API (e.g. a static file
    # server, or a different port during development) without extra setup. If the frontend is
    # served BY this same Flask app (see the "/" route below), this is same-origin anyway and
    # these headers are simply harmless no-ops.
    @app.after_request
    def add_cors_headers(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return resp

    @app.route("/api/<path:_any>", methods=["OPTIONS"])
    def cors_preflight(_any):
        return ("", 204)

    # ---- serve the bundled frontend (daftar-darayi.html) at "/" ----
    # This makes the whole app same-origin (no CORS needed at all) and means running the
    # backend is enough — "python run.py", then open http://localhost:5000 in a browser.
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

    @app.get("/")
    def serve_frontend():
        return send_from_directory(frontend_dir, "daftar-darayi.html")

    @app.get("/<path:filename>")
    def serve_frontend_asset(filename):
        # Only ever serves files that actually exist in frontend/ (e.g. if you later split out
        # a separate .css/.js file) — anything else correctly falls through to Flask's 404.
        full_path = os.path.join(frontend_dir, filename)
        if os.path.isfile(full_path):
            return send_from_directory(frontend_dir, filename)
        return jsonify({"error": "یافت نشد."}), 404

    # ---- blueprints ----
    from .routes.auth_routes import bp as auth_bp
    from .routes.portfolios import bp as portfolios_bp
    from .routes.transactions import bp as transactions_bp
    from .routes.holdings import bp as holdings_bp
    from .routes.withdrawals import bp as withdrawals_bp
    from .routes.prices import bp as prices_bp
    from .routes.ladders import bp as ladders_bp
    from .routes.secure_profit import bp as secure_profit_bp
    from .routes.snapshots import bp as snapshots_bp
    from .routes.users import bp as users_bp
    from .routes.categories import bp as categories_bp
    from .routes.accounts import bp as accounts_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(portfolios_bp, url_prefix="/api/portfolios")
    app.register_blueprint(transactions_bp, url_prefix="/api")
    app.register_blueprint(holdings_bp, url_prefix="/api/portfolios")
    app.register_blueprint(withdrawals_bp, url_prefix="/api")
    app.register_blueprint(prices_bp, url_prefix="/api/prices")
    app.register_blueprint(ladders_bp, url_prefix="/api/portfolios")
    app.register_blueprint(secure_profit_bp, url_prefix="/api/portfolios")
    app.register_blueprint(snapshots_bp, url_prefix="/api/portfolios")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(categories_bp, url_prefix="/api/categories")
    app.register_blueprint(accounts_bp, url_prefix="/api/accounts")

    @app.errorhandler(ApiError)
    def handle_api_error(err: ApiError):
        return jsonify({"error": err.message}), err.status_code

    @app.errorhandler(404)
    def handle_404(_err):
        return jsonify({"error": "یافت نشد."}), 404

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True})

    return app
