# StarPrivacyBot

An educational, open-source Telegram bot that demonstrates the official
**Telegram Bot API "Business" features** (Bot API 7.2+): when a Telegram
Business account owner connects the bot, it keeps a private backup copy of
incoming messages so the owner can still see what was sent to them even if
the sender later edits or deletes it.

This project exists to teach how the Business API, SQLAlchemy-backed
storage, and Telegram Stars payments fit together in a real bot. It is
**not** a spying tool for third-party accounts: it only ever sees messages
inside a Business chat that its owner has explicitly connected it to, using
Telegram's own in-app settings.

## ⚠️ Privacy & legal disclaimer

- This bot only works with Telegram's official **Business connection**
  feature. It can only see messages in chats belonging to a Business account
  that its owner deliberately connects, from Telegram Settings → Business →
  Chatbots. It has no way to access anyone else's chats.
- **The other side of the conversation (your customers) is very likely not
  aware their messages are being archived and monitored for edits/deletes.**
  Depending on your jurisdiction, recording or retaining a private
  conversation without the other party's knowledge or consent may be
  restricted or illegal (wiretapping / data protection / consumer protection
  laws vary by country and by whether the account is used for personal or
  business purposes). **You are solely responsible for using this software
  in compliance with the law that applies to you and for being transparent
  with people you talk to**, e.g. via a note in your business profile or
  chat greeting.
- Secret chats are never accessible through the Business API — Telegram does
  not deliver them to bots at all, so this project cannot and does not touch
  them.
- Nothing is stored before a Business connection is enabled, and archiving
  stops immediately when the connection is disabled.
- Treat the local database and media folder as sensitive personal data:
  encrypt the disk, restrict file permissions, and back it up securely.
- This code is provided for learning purposes, "as is", with no warranty.

## Features

- **Message archiving** — text, photos, videos, voice notes and documents
  sent *to* a connected Business account are copied (metadata + a local copy
  of the media file) as soon as they arrive.
- **Edit alerts** — if an archived message is edited, the owner gets a
  private message from the bot showing the original text, the new text, and
  the time of the edit.
- **Delete alerts** — if an archived message is deleted, the owner gets a
  private message with the original content (text and/or the cached media
  file) and when it was originally sent.
- **Only incoming messages** — messages the business owner sends themselves
  are never archived, only messages sent to them.
- **Subscriptions via Telegram Stars** — Basic and Premium monthly plans,
  paid with native Telegram Stars (`XTR`), no external payment provider
  needed.
- **2-day free trial** — every new user gets a one-time, no-payment trial
  (unlimited history retention) automatically granted on their first
  `/start`, so they can try the bot before subscribing.
- **Lifetime free admin** — Telegram user ID `1283428247` always has full,
  unmetered access; other admins can be added via `EXTRA_ADMIN_IDS`.
- **SQLite by default, PostgreSQL-ready** — swap `DATABASE_URL` to move from
  a single-VPS SQLite file to Postgres, no code changes required.
- **Russian-language UI** — all bot-facing text (commands, alerts, invoices)
  is in Russian; this codebase and its comments remain in English.

## How the Business API integration works

1. The account owner enables the bot in **Telegram Settings → Business →
   Chatbots** and picks which chats it should be active for.
2. Telegram sends the bot a `business_connection` update
   (`handlers/business.py::on_business_connection`); the bot stores the
   connection and its permissions (e.g. whether it's allowed to reply).
3. From then on, every new message in an enabled chat arrives as a
   `business_message` update. The bot checks that the connection is enabled
   and the owner has an active subscription (or is an admin) before storing
   anything (`handlers/business.py::on_business_message`).
4. If a stored message is later changed, Telegram sends
   `edited_business_message`; if it's deleted, Telegram sends
   `deleted_business_messages`. Both are handled to notify the owner with
   the original content.

All of this relies purely on official Bot API updates — no scraping, no
unofficial client libraries, no MTProto session hijacking.

## Project structure

```
starprivacy/
├── main.py                  # entry point, aiogram Dispatcher + polling loop
├── config.py                # env-driven configuration, tariffs, admin IDs
├── requirements.txt
├── .env.example
├── database/
│   ├── models.py             # SQLAlchemy ORM models
│   └── db.py                 # async engine/session + CRUD helpers
├── handlers/
│   ├── business.py           # business_connection / message / edit / delete
│   ├── subscription.py       # /subscribe, Stars invoices & payments
│   ├── commands.py           # /start /help /status
│   └── admin.py               # /stats (admin only)
├── middlewares/
│   └── access.py              # subscription/access-level resolution
├── utils/
│   └── media.py                # media download/caching helpers
└── webapp/                    # Mini App: dashboard + archive browser
    ├── server.py                # aiohttp app factory, runs alongside polling
    ├── auth.py                  # Telegram `initData` HMAC validation
    ├── api.py                   # JSON API (status, tariffs, chats, messages, media)
    └── static/                  # vanilla HTML/CSS/JS frontend (no build step)
```

## Requirements

- Python 3.11+
- A bot token from [@BotFather](https://t.me/BotFather)
- A Telegram account with **Telegram Business** (Premium subscription
  required by Telegram to use Business features) to test the connection

## Local setup

```bash
git clone https://github.com/maratfaiz/starprivacy.git
cd starprivacy
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set BOT_TOKEN at minimum
python main.py
```

On first connection, in Telegram: **Settings → Business → Chatbots →
Add bot** and paste your bot's username, then choose which chats it should
be active in.

## Running it without your own computer (Railway)

The bot needs *some* machine online 24/7 - it doesn't have to be yours. The
quickest way to get one without touching a terminal is a PaaS like
[Railway](https://railway.app) (Render.com works the same way):

1. Push this repo to your own GitHub account if you haven't already (or use
   `maratfaiz/starprivacy` directly if Railway has access to it).
2. On [railway.app](https://railway.app), sign in, **New Project → Deploy
   from GitHub repo**, and pick this repository/branch. Railway detects
   `requirements.txt` and the `Procfile` automatically and starts building.
3. Add persistent storage: in the service, **New → Volume**, mount it at
   `/data`. Without this, the SQLite database and cached media are wiped on
   every redeploy.
4. Open the service's **Variables** tab and add:
   - `BOT_TOKEN` = your token from @BotFather
   - `DATABASE_URL` = `sqlite+aiosqlite:////data/starprivacy.db`
   - `MEDIA_STORAGE_PATH` = `/data/media`

   Leave `WEBAPP_HOST`/`WEBAPP_PORT`/`PORT` unset - Railway injects `PORT`
   itself and the app already binds to `0.0.0.0`.
5. Under **Settings → Networking**, click **Generate Domain**. Railway gives
   you a public `https://....up.railway.app` URL with TLS already handled -
   no ngrok, no Caddy, no reverse proxy to configure yourself.
6. Register that URL with BotFather: `/mybots` → select your bot → **Bot
   Settings** → **Configure Mini App** (or **Menu Button**) → paste it.
7. Message your bot, send `/start`, then connect it in Telegram: **Settings
   → Business → Chatbots → Add bot**.

Cost is typically covered by Railway's free trial credit initially, then a
few dollars a month on its Hobby plan for an always-on service plus a small
volume.

## Deploying to a VPS

These steps assume a fresh Ubuntu/Debian VPS and a non-root deploy user.

1. **Install prerequisites**

   ```bash
   sudo apt update && sudo apt install -y python3.11 python3.11-venv git
   ```

2. **Clone and configure**

   ```bash
   git clone https://github.com/maratfaiz/starprivacy.git
   cd starprivacy
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   nano .env   # set BOT_TOKEN, and DATABASE_URL if using PostgreSQL
   ```

3. **(Optional) Use PostgreSQL instead of SQLite**

   ```bash
   sudo apt install -y postgresql
   sudo -u postgres createuser starprivacy -P
   sudo -u postgres createdb -O starprivacy starprivacy
   # then in .env:
   # DATABASE_URL=postgresql+asyncpg://starprivacy:yourpassword@localhost:5432/starprivacy
   ```

4. **Run it as a systemd service** so it restarts on crash/reboot. Create
   `/etc/systemd/system/starprivacybot.service`:

   ```ini
   [Unit]
   Description=StarPrivacyBot
   After=network.target

   [Service]
   Type=simple
   User=deploy
   WorkingDirectory=/home/deploy/starprivacy
   EnvironmentFile=/home/deploy/starprivacy/.env
   ExecStart=/home/deploy/starprivacy/venv/bin/python main.py
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

   Then:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now starprivacybot
   sudo journalctl -u starprivacybot -f   # tail logs
   ```

5. **Back up `data/`** (SQLite file and cached media) regularly if you rely
   on the default SQLite setup — it holds all archived content.

The bot itself uses long polling, so it needs no inbound port. The **Mini App**
does, though — see the next section.

## Mini App (dashboard + archive browser)

The bot also serves a Telegram [Mini App](https://core.telegram.org/bots/webapps):
a small web dashboard showing your subscription/trial status and tariffs to
buy, plus an archive browser to page through saved chats and see edit/delete
history and cached media — all from inside Telegram. The UI is a dark,
gold-accented premium theme (Manrope/Inter, bottom sheets, a status hero
card) defined entirely in `webapp/static/`.

It runs as an aiohttp server (`webapp/server.py`) inside the same process as
the bot, listening on `WEBAPP_HOST:WEBAPP_PORT` (default `127.0.0.1:8080`,
i.e. not exposed publicly by itself).

**Telegram requires Mini App URLs to be HTTPS on a public domain**, so you
need a reverse proxy in front of it. The simplest option on a VPS is
[Caddy](https://caddyserver.com/), which handles Let's Encrypt automatically:

```bash
sudo apt install -y caddy
# /etc/caddy/Caddyfile
# yourdomain.example {
#     reverse_proxy 127.0.0.1:8080
# }
sudo systemctl reload caddy
```

Then register the URL with BotFather: `/mybots` → select your bot → **Bot
Settings** → **Configure Mini App** (or **Menu Button**) → set it to
`https://yourdomain.example`.

Every API request is authenticated using Telegram's signed `initData`
(`webapp/auth.py` validates the HMAC per Telegram's documented algorithm) —
there are no separate accounts or passwords, and a user can only ever see
their own connections/chats/messages, never anyone else's, regardless of
admin status.

## Subscriptions & Telegram Stars

- `/subscribe` shows the available plans and lets the user pick one; the bot
  sends a native Telegram Stars invoice (currency `XTR`) — Telegram settles
  the payment itself, no payment provider token needed.
- Plans and prices are defined in `config.py::TARIFFS`:
  - **Basic** — 100⭐/month, 14 days of message history retention.
  - **Premium** — 250⭐/month, unlimited history retention.
- Every new user gets a one-time **2-day free trial** (`config.py::TRIAL_TARIFF`),
  auto-granted on their first `/start` via `database.db.grant_trial_if_eligible`
  — no payment, no manual action, and it can't be re-triggered once used
  (tracked by `User.trial_used`).
- Telegram user ID `1283428247` bypasses subscriptions entirely (permanent
  free admin access) — see `config.py::LIFETIME_FREE_ADMIN_ID`.
- `/status` shows the caller's current plan, trial/subscription expiry, and
  connection state.

## Disclaimer

This is a learning project for understanding the Telegram Bot API's
Business features, async database access with SQLAlchemy, and Stars-based
payments. Review the privacy section above before using it with real
conversations, and adapt the disclaimers/consent flow to your local laws
before any production use.
