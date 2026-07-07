# CLAUDE.md

This file gives AI assistants (Claude Code and others) the context they need to work in this repository.

## Project purpose

`starprivacy` (StarPrivacyBot) is an educational, open-source Telegram bot built on the official
Bot API "Business" features. When a Telegram Business account owner connects the bot, it archives
incoming messages so the owner can still see them if the sender edits or deletes them, and gates
that feature behind a Telegram Stars subscription. See `README.md` for the full feature list and
the privacy/legal disclaimer that must stay in sync with actual behavior.

## Tech stack

- Python 3.11+, [aiogram 3](https://docs.aiogram.dev/) for the Bot API client/dispatcher
- SQLAlchemy 2.0 async ORM, SQLite (`aiosqlite`) by default, PostgreSQL (`asyncpg`) in production
- Telegram Stars (`XTR` currency) for payments, no external payment provider

## Getting started

- Install dependencies: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- Configure: `cp .env.example .env` and set `BOT_TOKEN` at minimum
- Run the bot locally: `python main.py` (long polling, no inbound port needed)
- No test suite yet; sanity-check changes with `python -m py_compile` and a manual import check
  (`python -c "from handlers import build_root_router; build_root_router()"`) since there's no
  CI harness in this repo yet.

## Directory structure

- `main.py` — entry point: builds the aiogram `Bot`/`Dispatcher`, registers the allowed Business
  API update types, starts polling.
- `config.py` — all environment-driven configuration: bot token, database URL, media storage path,
  admin IDs (including the hardcoded lifetime-free admin), and subscription tariffs.
- `database/models.py` — SQLAlchemy ORM models (`User`, `BusinessConnection`, `Subscription`,
  `SavedMessage`). `User.trial_used` gates the one-time free trial.
- `database/db.py` — async engine/session setup and all CRUD helper functions; handlers should go
  through this module rather than touching SQLAlchemy sessions directly.
- `handlers/business.py` — the core feature: `business_connection`, `business_message`,
  `edited_business_message`, `deleted_business_messages` handlers. This is where the "only archive
  incoming messages, after subscription is active" gating logic lives.
- `handlers/subscription.py` — `/subscribe` command, Stars invoice creation, pre-checkout and
  successful-payment handlers.
- `handlers/commands.py` — `/start`, `/help`, `/status`.
- `handlers/admin.py` — `/stats`, restricted to `config.ADMIN_IDS`.
- `middlewares/access.py` — resolves whether a business owner currently has usable access
  (admin override vs. active paid subscription vs. none).
- `utils/media.py` — downloads/caches media (photo/video/voice/document) referenced by a message.
- `webapp/` — the Telegram Mini App: `server.py` builds/runs the aiohttp app (started as a background
  task in `main.py`, alongside bot polling), `auth.py` validates Telegram's signed `initData`,
  `api.py` is the JSON API (status/tariffs/subscribe/connections/chats/messages/media), and
  `static/` is a plain HTML/CSS/JS frontend (no build step, no framework).

## Key conventions

- Never store or process anything for a Business connection that is disabled, or for a user
  without an active subscription/admin override — that gating must stay centralized in
  `middlewares/access.py` and be checked in `handlers/business.py`, not duplicated ad hoc.
- Only *incoming* messages (sent to the business account) are archived; messages the business
  owner sends themselves must never be stored — see the `is_from_business_owner` checks.
- All bot-facing strings (commands, alerts, invoices) are in Russian; keep new user-facing text
  consistent with that. Code, comments, and docs stay in English.
- The trial tariff (`config.TRIAL_TARIFF`) is intentionally excluded from `config.TARIFFS` (the
  purchasable plans shown in `/subscribe`) — it's granted programmatically once per user, never
  bought.
- Every Mini App API route must go through `webapp.auth.validate_init_data` (enforced globally by
  `webapp.api.auth_middleware`) and re-check that the requested connection/chat/message belongs to
  the authenticated Telegram user — admin status never grants visibility into another user's data.
- Secrets (bot token, DB credentials) come from environment variables only — never hardcode them.
  The one intentional exception is `config.LIFETIME_FREE_ADMIN_ID`, which is a product decision,
  not a secret.
- Prefer small, focused commits with clear messages.
- Keep this CLAUDE.md and `README.md` in sync whenever the project structure, tooling, or
  workflows change.
