from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Stand(db.Model):
    __tablename__ = "stands"

    id = db.Column(db.String(10), primary_key=True)
    status = db.Column(db.String(20), nullable=False, default="free")
    flight_number = db.Column(db.String(20), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Weather(db.Model):
    __tablename__ = "weather"

    id = db.Column(db.Integer, primary_key=True)
    icao = db.Column(db.String(8), nullable=False, unique=True, index=True)
    metar = db.Column(db.Text, nullable=False, default="")
    taf = db.Column(db.Text, nullable=False, default="")
    updated_by = db.Column(db.String(80), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


def seed_data():
    existing_ids = {stand.id for stand in Stand.query.all()}
    for prefix in ("A", "B"):
        for number in range(1, 21):
            stand_id = f"{prefix}{number:02d}"
            if stand_id not in existing_ids:
                db.session.add(
                    Stand(
                        id=stand_id,
                        status="free",
                        flight_number=None,
                        updated_at=datetime.utcnow(),
                    )
                )
    db.session.commit()


def seed_admin_user(username: str, password: str):
    existing = User.query.filter_by(username=username).first()
    if existing is None:
        admin = User(username=username, role="admin", active=True)
        admin.set_password(password)
        db.session.add(admin)
    else:
        existing.role = "admin"
        existing.active = True
        existing.set_password(password)
    db.session.commit()


def seed_user(username: str, password: str, role: str):
    existing = User.query.filter_by(username=username).first()
    if existing is None:
        user = User(username=username, role=role, active=True)
        user.set_password(password)
        db.session.add(user)
    else:
        existing.role = role
        existing.active = True
        existing.set_password(password)
    db.session.commit()
