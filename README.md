# plex-tg-bot

Self-hostable Telegram bot that lets your friends request access to your Plex server. One admin click in a private group sends an invite. After acceptance, the bot exposes shortcuts to apps, web player, and Overseerr.

[![CI](https://github.com/AndrewGolikov55/plex-tg-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/AndrewGolikov55/plex-tg-bot/actions/workflows/ci.yml)
[![Release](https://github.com/AndrewGolikov55/plex-tg-bot/actions/workflows/release.yml/badge.svg)](https://github.com/AndrewGolikov55/plex-tg-bot/actions/workflows/release.yml)

## Features

- Open `/request` flow with admin approval via inline buttons in a private chat
- Email validation (format + MX) before approval
- Pre-import to Overseerr on approve (best-effort, optional)
- Adaptive `/start` menu by user state: `no_access` | `pending` | `has_access`
- Customizable apps screen rendered from a markdown file you provide
- Daily reconciliation with Plex (cron, default 04:00) — detects users you revoked manually
- Admin commands: `/admin list`, `/admin pending`, `/admin sync`
- HTTP/SOCKS proxy support for Telegram-blocked regions
- i18n: ships with English and Russian; add a locale via one PR
- Observability: `/healthz` and Prometheus `/metrics` on port 9095

## Quick start

Two ways to run:

### A. Plain `docker compose` (recommended for simple self-hosters)

```bash
git clone https://github.com/AndrewGolikov55/plex-tg-bot.git
cd plex-tg-bot
cp .env.example .env
# edit .env — at minimum set TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, PLEX_TOKEN
mkdir -p data
docker compose up -d
docker compose logs -f
```

The bot starts on host port `9095` exposing `/healthz` and `/metrics`. SQLite state lives in `./data/db.sqlite`.

To customize the apps screen, edit `src/plex_tg_bot/i18n/apps/<lang>.html` in your fork (or open a PR).

### B. Portainer (GitOps)

Create a stack pointing to this repo:

- Repository: `https://github.com/AndrewGolikov55/plex-tg-bot.git`
- Compose path: `docker-compose.yml`
- Environment variables: paste from your `.env` (or set individually)

Set `PLEX_BOT_DATA_BIND` to the **parent** directory on the host (e.g. `/mnt/user/VmBOX/docker/plex-bot`) — the manifest appends `/data` itself. Make sure that directory is owned by UID 1000 (the in-container `bot` user).

Portainer will pull the manifest on every release.

#### Auto-redeploy (CD)

The release workflow can hit a Portainer GitOps webhook after a successful image build, so each new tag goes live without a manual click. Set the repo secret `PORTAINER_WEBHOOK` to your stack's full webhook URL (host + UUID); it's masked from logs. If unset the redeploy step is skipped.

### Local development

Use `docker-compose.dev.yml` to build and run the bot from your local source:

```bash
cp .env.example .env
# fill in
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up
```

`./src` is bind-mounted, so edit code and restart the container — no rebuild needed for Python changes.

## Configuration

All configuration is via environment variables. See `.env.example` for the full list with defaults.

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | — | Token from @BotFather |
| `ADMIN_CHAT_ID` | yes | — | Private group or DM where approval cards land |
| `PLEX_TOKEN` | yes | — | Server owner's `X-Plex-Token` |
| `PLEX_SERVER_NAME` | no | auto | Override; otherwise discovered from the API |
| `PLEX_MACHINE_IDENTIFIER` | no | auto | Override; otherwise discovered from the API |
| `OVERSEERR_PUBLIC_URL` | no | — | When unset, the Overseerr button is hidden |
| `OVERSEERR_API_KEY` | conditional | — | Required when `OVERSEERR_PUBLIC_URL` is set |
| `WATCH_URL` | no | `https://app.plex.tv/desktop/` | "Watch in browser" link |
| `DB_PATH` | no | `/data/db.sqlite` | SQLite database location |
| `BOT_LANG` | no | `en` | `en` or `ru` |
| `PROXY_URL` | no | — | e.g. `socks5://192.168.0.1:1080` or `http://proxy:7890` |
| `NO_PROXY` | no | `localhost,127.0.0.1` | Comma-separated bypass list |
| `HEALTH_PORT` | no | `9095` | Port for `/healthz` and `/metrics` |
| `LOG_LEVEL` | no | `INFO` | Python logging level |
| `DAILY_SYNC_CRON` | no | `0 4 * * *` | Crontab expression for daily reconciliation |
| `SHARED_LIBRARY_IDS` | no | `[]` (= all) | Comma-separated Plex section IDs to share |
| `ALLOW_SYNC` | no | `1` | Plex sharing flag: allow sync |
| `ALLOW_CAMERA_UPLOAD` | no | `0` | Plex sharing flag: allow camera upload |
| `ALLOW_CHANNELS` | no | `0` | Plex sharing flag: allow channels |

## Customization

### Apps screen

The "Get apps" message is loaded at runtime from `src/plex_tg_bot/i18n/apps/<lang>.html` (Telegram-flavoured HTML, baked into the image). To customize: edit the file in your fork or open a PR. To add a new language: drop a new `<lang>.html` next to the existing files; the locale parity test will pick it up.

### Locales

`src/plex_tg_bot/i18n/<lang>.yml` plus `src/plex_tg_bot/i18n/apps/<lang>.html` — add a new pair (matching the keys in `en.yml`) and set `BOT_LANG=<lang>`. PRs welcome.

## Architecture

Single asyncio process:

```
aiogram (Telegram long-polling)
  └─ handlers (bot/, services/)
       ├─ aiosqlite  ──────────────────── /data/db.sqlite
       ├─ httpx (PlexAPI + Overseerr)
       └─ APScheduler (daily sync cron)

aiohttp server (separate task)
  └─ /healthz  /metrics  ──────────────── :9095
```

Long polling is used (not webhooks) — symmetric outbound traffic, no public HTTPS endpoint required.

## FAQ

**Why long polling and not webhook?**
Long polling is symmetric outbound traffic — no public HTTPS endpoint or TLS certificate is needed. The workload (tens of messages per day) does not benefit from webhook latency.

**Telegram is blocked in my country — how do I configure a proxy?**
Set `PROXY_URL=socks5://...` (or `http://...`). The bot routes Telegram and Plex API traffic through it. Use `NO_PROXY` to bypass for internal hosts (e.g. your local Plex IP).

**My `ADMIN_CHAT_ID` looks like a positive number — why did it stop working?**
Telegram groups have negative chat ids (often starting with `-100`). DMs have positive ids. Verify by sending a message to @userinfobot in the same chat.

**The bot approved the invite but the user sees "no servers available".**
The Plex invite email sometimes takes a few minutes to process. Ask the user to wait and refresh.

## Contributing

```bash
git clone https://github.com/AndrewGolikov55/plex-tg-bot.git
cd plex-tg-bot
uv venv
uv pip install -e ".[dev]"
uv run pytest
```

PRs welcome — please add tests and ensure `ruff` and `mypy` stay clean.

To add a locale: copy `src/plex_tg_bot/i18n/en.yml` to `<lang>.yml`, translate the values, run `uv run pytest tests/test_locales.py`.

## License

MIT — see `LICENSE`.
