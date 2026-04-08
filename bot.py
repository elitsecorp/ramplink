from datetime import datetime

from telegram import Update

from models import Stand, db


def parse_stand_message(text: str):
    parsed = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue

        stand_id = parts[0].upper()
        value = parts[1].strip()
        value_upper = value.upper()

        if value_upper == "EMPTY":
            status = "free"
            flight_number = None
        elif value_upper == "BLOCKED":
            status = "blocked"
            flight_number = None
        else:
            status = "occupied"
            flight_number = value_upper

        parsed.append(
            {
                "stand_id": stand_id,
                "status": status,
                "flight_number": flight_number,
            }
        )
    return parsed


def process_telegram_update(update: Update, allowed_ids):
    user = update.effective_user
    message = update.effective_message

    if not user or not message or not message.text:
        return {"processed": 0, "authorized": False, "reason": "missing message"}

    if user.id not in allowed_ids:
        return {"processed": 0, "authorized": False, "reason": "unauthorized"}

    parsed_lines = parse_stand_message(message.text)
    for entry in parsed_lines:
        stand = Stand.query.filter_by(id=entry["stand_id"]).first()
        if stand is None:
            stand = Stand(id=entry["stand_id"])
            db.session.add(stand)

        stand.status = entry["status"]
        stand.flight_number = entry["flight_number"]
        stand.updated_at = datetime.utcnow()

    db.session.commit()
    return {"processed": len(parsed_lines), "authorized": True, "reason": "ok"}
