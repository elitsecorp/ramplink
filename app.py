import os
from collections import Counter
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import inspect, text
from telegram import Bot, Update

from bot import process_telegram_update
from models import Stand, User, Weather, db, seed_admin_user, seed_data, seed_user

ATC_TOKEN = "atc123"
OPS_TOKEN = "ops123"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7971065104:AAG81Pw-1UYsrZ9V2QGdWgnPIE3YDYszb_4")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ATC_USERNAME = os.getenv("ATC_USERNAME", "atc")
ATC_PASSWORD = os.getenv("ATC_PASSWORD", "atc123")
IOCC_USERNAME = os.getenv("IOCC_USERNAME", "iocc")
IOCC_PASSWORD = os.getenv("IOCC_PASSWORD", "iocc123")


def parse_allowed_telegram_user_ids():
    raw = os.getenv("ALLOWED_TELEGRAM_USER_IDS", "123456789")
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids or [123456789]


def create_app() -> Flask:
    app = Flask(__name__)
    database_url = os.getenv("DATABASE_URL")
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    if not database_url:
        database_path = Path(__file__).resolve().parent / "database.db"
        database_url = f"sqlite:///{database_path.as_posix()}"

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "ramplink-lite")
    app.config["ATC_TOKEN"] = ATC_TOKEN
    app.config["OPS_TOKEN"] = OPS_TOKEN
    app.config["ALLOWED_TELEGRAM_USER_IDS"] = parse_allowed_telegram_user_ids()
    app.config["ADMIN_USERNAME"] = ADMIN_USERNAME
    app.config["ADMIN_PASSWORD"] = ADMIN_PASSWORD
    app.config["ATC_USERNAME"] = ATC_USERNAME
    app.config["ATC_PASSWORD"] = ATC_PASSWORD
    app.config["IOCC_USERNAME"] = IOCC_USERNAME
    app.config["IOCC_PASSWORD"] = IOCC_PASSWORD

    db.init_app(app)

    with app.app_context():
        db.create_all()
        ensure_schema()
        seed_data()
        seed_admin_user(app.config["ADMIN_USERNAME"], app.config["ADMIN_PASSWORD"])
        seed_user(app.config["ATC_USERNAME"], app.config["ATC_PASSWORD"], "atc")
        seed_user(app.config["IOCC_USERNAME"], app.config["IOCC_PASSWORD"], "iocc")

    app.extensions["telegram_bot"] = Bot(TELEGRAM_BOT_TOKEN)

    @app.before_request
    def load_current_user():
        session_user_id = session.get("user_id")
        request.current_user = None
        if session_user_id:
            request.current_user = db.session.get(User, session_user_id)
            if request.current_user is None or not request.current_user.active:
                session.clear()

    @app.route("/")
    def index():
        if current_user():
            return redirect(url_for("dashboard"))
        icao = request.args.get("icao", "").strip().upper()
        weather = Weather.query.filter_by(icao=icao).first() if icao else None
        latest_weather = Weather.query.order_by(Weather.updated_at.desc()).first()
        return render_template(
            "home.html",
            icao=icao,
            weather=weather,
            latest_weather=latest_weather,
        )

    @app.route("/favicon.ico")
    def favicon():
        return ("", 204)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user():
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = User.query.filter_by(username=username, active=True).first()

            if user and user.check_password(password):
                session.clear()
                session["user_id"] = user.id
                user.last_login_at = datetime.utcnow()
                db.session.commit()
                return redirect(url_for("dashboard"))

            flash("Invalid username or password.")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        user = current_user()
        stands = Stand.query.order_by(Stand.id.asc()).all()
        counts = Counter(stand.status for stand in stands)
        weather_list = Weather.query.order_by(Weather.updated_at.desc()).all()
        users = []
        if user.role == "admin":
            users = User.query.order_by(User.role.asc(), User.username.asc()).all()

        latest_weather = weather_list[0] if weather_list else None
        return render_template(
            "dashboard.html",
            user=user,
            stands=stands,
            counts=counts,
            weather_list=weather_list,
            latest_weather=latest_weather,
            users=users,
            show_stands=user.role == "atc",
            show_weather_editor=user.role == "iocc",
            show_admin=user.role == "admin",
        )

    @app.route("/admin")
    @login_required
    def admin_panel():
        user = current_user()
        if user.role != "admin":
            abort(403)
        return redirect(url_for("dashboard"))

    @app.route("/users/create", methods=["POST"])
    @login_required
    def create_user():
        user = current_user()
        if user.role != "admin":
            abort(403)

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "").strip().lower()

        if role not in {"marshaller", "atc", "iocc"}:
            flash("Choose a valid role.")
            return redirect(url_for("dashboard"))

        if not username or not password:
            flash("Username and password are required.")
            return redirect(url_for("dashboard"))

        if User.query.filter_by(username=username).first():
            flash("That username already exists.")
            return redirect(url_for("dashboard"))

        new_user = User(username=username, role=role, active=True)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash(f"Created {role} account for {username}.")
        return redirect(url_for("dashboard"))

    @app.route("/telegram/webhook", methods=["POST"])
    def telegram_webhook():
        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({"ok": True, "ignored": "empty payload"})

        telegram_bot = app.extensions["telegram_bot"]
        update = Update.de_json(payload, telegram_bot)
        result = process_telegram_update(update, app.config["ALLOWED_TELEGRAM_USER_IDS"])
        return jsonify({"ok": True, "processed": result})

    @app.route("/stands", methods=["GET"])
    @login_required
    def stands_api():
        user = current_user()
        if user.role != "atc":
            abort(403)
        stands = Stand.query.order_by(Stand.id.asc()).all()
        return jsonify(
            [
                {
                    "id": stand.id,
                    "status": stand.status,
                    "flight_number": stand.flight_number,
                    "updated_at": stand.updated_at.isoformat() if stand.updated_at else None,
                }
                for stand in stands
            ]
        )

    @app.route("/weather/<icao>", methods=["GET"])
    def weather_api(icao):
        weather = Weather.query.filter_by(icao=icao.upper()).first()
        if not weather:
            return jsonify({"error": "weather not found"}), 404
        return jsonify(
            {
                "icao": weather.icao,
                "metar": weather.metar,
                "taf": weather.taf,
                "updated_by": weather.updated_by,
                "updated_at": weather.updated_at.isoformat() if weather.updated_at else None,
            }
        )

    @app.route("/weather/update", methods=["POST"])
    @login_required
    def weather_update():
        user = current_user()
        if user.role != "iocc":
            abort(403)

        payload = request.get_json(silent=True) or request.form
        icao = payload.get("icao", "").strip().upper()
        metar = payload.get("metar", "").strip()
        taf = payload.get("taf", "").strip()

        if not icao:
            return jsonify({"error": "ICAO is required"}), 400

        weather = Weather.query.filter_by(icao=icao).first()
        if weather is None:
            weather = Weather(
                icao=icao,
                metar=metar,
                taf=taf,
                updated_by=user.username,
                updated_at=datetime.utcnow(),
            )
            db.session.add(weather)
        else:
            weather.metar = metar
            weather.taf = taf
            weather.updated_by = user.username
            weather.updated_at = datetime.utcnow()

        db.session.commit()

        if request.accept_mimetypes.best == "application/json":
            return jsonify({"ok": True, "icao": icao, "updated_by": user.username})
        return redirect(url_for("dashboard"))

    @app.route("/atc/<token>", methods=["GET"])
    @login_required
    def atc_view(token):
        user = current_user()
        if user.role != "atc":
            abort(403)
        if token != app.config["ATC_TOKEN"]:
            abort(403)
        stands = Stand.query.order_by(Stand.id.asc()).all()
        counts = Counter(stand.status for stand in stands)
        return render_template(
            "atc.html",
            stands=stands,
            token=token,
            counts=counts,
        )

    @app.route("/ops/<token>", methods=["GET"])
    def ops_view(token):
        if token != app.config["OPS_TOKEN"]:
            abort(403)
        weather_list = Weather.query.order_by(Weather.updated_at.desc()).all()
        return render_template(
            "ops.html",
            token=token,
            weather_list=weather_list,
        )

    @app.route("/weather", methods=["GET", "POST"])
    def pilot_weather():
        icao = ""
        weather = None

        if request.method == "POST":
            icao = request.form.get("icao", "").strip().upper()
        else:
            icao = request.args.get("icao", "").strip().upper()

        if icao:
            weather = Weather.query.filter_by(icao=icao).first()

        return render_template("weather.html", icao=icao, weather=weather)

    return app


def current_user():
    user = getattr(request, "current_user", None)
    if user is not None:
        return user
    session_user_id = session.get("user_id")
    if not session_user_id:
        return None
    return db.session.get(User, session_user_id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def ensure_schema():
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())

    if "weather" in table_names:
        weather_columns = {column["name"] for column in inspector.get_columns("weather")}
        if "updated_by" not in weather_columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE weather ADD COLUMN updated_by VARCHAR(80)"))


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "0") == "1")
