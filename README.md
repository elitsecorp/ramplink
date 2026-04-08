# RampLink Lite

RampLink Lite is a minimal Flask-based airport coordination system with Telegram stand updates, secure web links for ATC, a password-protected IOCC dashboard for weather editing, and a pilot weather lookup page.

## What it does

- Marshalls send stand assignments through Telegram
- ATC views stand status in a read-only web page
- IOCC updates METAR and TAF through a protected login
- Admin users can create ATC, IOCC, and marshaller accounts
- Pilots request weather by ICAO code

## Project files

- [app.py](./app.py)
- [bot.py](./bot.py)
- [models.py](./models.py)
- [templates/atc.html](./templates/atc.html)
- [templates/ops.html](./templates/ops.html)
- [templates/home.html](./templates/home.html)
- [templates/login.html](./templates/login.html)
- [templates/dashboard.html](./templates/dashboard.html)
- [templates/weather.html](./templates/weather.html)
- [static/style.css](./static/style.css)
- [requirements.txt](./requirements.txt)

## Requirements

- Python 3.10+
- A Telegram bot token from BotFather
- A public HTTPS URL for the Telegram webhook

## Install

```bash
pip install -r requirements.txt
```

## Configure

Set your Telegram bot token before starting Flask.

PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN="123456:your-real-token"
```

You can also set:

```powershell
$env:SECRET_KEY="some-secret-value"
```

Allowed Telegram sender IDs are read from `ALLOWED_TELEGRAM_USER_IDS` as a comma-separated list.

The first admin account is created automatically on startup:

- Username: `admin`
- Password: `admin123`

The first ATC and IOCC accounts are created automatically on startup:

- ATC username: `atc`
- ATC password: `atc123`
- IOCC username: `iocc`
- IOCC password: `iocc123`

You can override those with environment variables:

```powershell
$env:ADMIN_USERNAME="your-admin-name"
$env:ADMIN_PASSWORD="your-admin-password"
$env:ATC_USERNAME="your-atc-name"
$env:ATC_PASSWORD="your-atc-password"
$env:IOCC_USERNAME="your-iocc-name"
$env:IOCC_PASSWORD="your-iocc-password"
```

## Run locally

```bash
python app.py
```

The app uses a SQLite database stored at `database.db` in the project root.

## Deploy on Railway

1. Push this repository to GitHub.
2. In Railway, create a new project from the GitHub repo.
3. Add a PostgreSQL database to the Railway project.
4. Set these environment variables in Railway:

```text
SECRET_KEY=your-long-random-secret
TELEGRAM_BOT_TOKEN=your-bot-token
PUBLIC_BASE_URL=https://<your-app>.up.railway.app
ADMIN_USERNAME=admin
ADMIN_PASSWORD=choose-a-strong-password
ATC_USERNAME=atc
ATC_PASSWORD=choose-a-strong-password
IOCC_USERNAME=iocc
IOCC_PASSWORD=choose-a-strong-password
ALLOWED_TELEGRAM_USER_IDS=123456789
```

5. Railway will supply `PORT` automatically. The app and `Procfile` already use it.
6. Railway will also supply `DATABASE_URL` from the Postgres plugin. The app uses it automatically.
7. Set `PUBLIC_BASE_URL` to your Railway app URL so the bot can register its webhook on startup.
8. Deploy the service.

After deployment:
- Open `/login` for staff access
- Open `/` or `/weather` for public weather lookup

If the bot still looks idle, check Railway logs for `Telegram webhook configured` or `Failed to configure Telegram webhook`. The most common causes are a wrong `PUBLIC_BASE_URL`, a mismatched `ALLOWED_TELEGRAM_USER_IDS`, or an invalid bot token.

If you want to keep using SQLite instead of Postgres, you will need a persistent Railway volume. Postgres is the safer Railway choice.

## Telegram setup

1. Create a bot with BotFather.
2. Copy the bot token into `TELEGRAM_BOT_TOKEN`.
3. Deploy the Flask app behind HTTPS.
4. Set the webhook:

```bash
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://your-domain.example/telegram/webhook
```

## Routes

- `GET /`
- `GET /login`
- `GET /logout`
- `GET /dashboard`
- `POST /users/create`
- `POST /telegram/webhook`
- `GET /stands`
- `GET /weather/<icao>`
- `POST /weather/update`
- `GET /atc/atc123`
- `GET /ops/ops123`
- `GET /weather`

## Access

- Home: `/`
- Public pilot weather: `/weather`
- ATC: `/atc/atc123`
- Staff login: `/login`
- Protected dashboard: `/dashboard`
- Admin panel: shown inside the dashboard for admin users
- Legacy Ops token view: `/ops/ops123` for read-only weather viewing
- Stand JSON API: `/stands` for logged-in ATC users
- Weather update form: visible only to logged-in IOCC users

ATC users see stand assignments only after logging in to the dashboard.
Anyone can view weather on `/` or `/weather`.

The token-based ATC and Ops routes still return `403` if the token does not match.

## Example Telegram message

```text
A12 ET302
A13 ET405
B01 EMPTY
C07 BLOCKED
```

Parsed behavior:

- `ET302` and `ET405` become occupied stands
- `EMPTY` becomes free
- `BLOCKED` becomes blocked

## Weather audit trail

Each saved weather record stores the username of the staff member who last updated it. The pilot view and staff views display that name.

## Notes

- Stand records are preloaded for `A01-A20` and `B01-B20`
- ATC communication stays unchanged
- The login system is intentionally simple and session-based
