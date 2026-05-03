# plex-tg-bot

[English](README.md) · [Русский](README.ru.md)

Self-hostable Telegram bot that lets your friends request access to your Plex server. One admin tap in a private chat sends an invite. After acceptance, the bot exposes shortcuts to apps, the web player, and Overseerr.

## Screenshots

<p align="center">
  <img src="docs/screenshots/start-no-access.png" alt="/start menu for a new user" width="300">
  <img src="docs/screenshots/request-flow.png"   alt="/request flow"             width="300">
  <img src="docs/screenshots/admin-panel.png"    alt="Admin panel"               width="300">
</p>

<sub>Drop your own PNGs into <code>docs/screenshots/</code> — see <code>docs/screenshots/README.md</code> for the expected filenames.</sub>

## Features

- Open `/request` flow — friend types email and a referrer note, admin gets an inline-button approval card.
- One-tap approve: bot calls Plex API to share the server, pre-imports the user into Overseerr, DMs them.
- Admin inline panel: paginated user list with per-row revoke (Plex API + DB) and confirmation card.
- Adaptive `/start` menu by user state (`no_access` / `pending` / `has_access`).
- Daily reconciliation with Plex (default 04:00) — detects users you revoked manually in Plex Web.
- HTTP / SOCKS proxy support for Telegram-blocked regions.
- i18n: ships with English and Russian, switch via `BOT_LANG`.
- `/healthz` and Prometheus `/metrics` for observability.

## Quick start

### Plain `docker compose`

```bash
git clone https://github.com/AndrewGolikov55/plex-tg-bot.git
cd plex-tg-bot
cp .env.example .env
# edit .env — at minimum set TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, PLEX_TOKEN
mkdir -p data
docker compose up -d
docker compose logs -f
```

The bot starts on port `9095` exposing `/healthz` and `/metrics`. SQLite state lives in `./data/db.sqlite`.

### Portainer (GitOps)

Create a stack pointing to this repo:

- Repository: `https://github.com/AndrewGolikov55/plex-tg-bot.git`
- Compose path: `docker-compose.yml`
- Environment variables: paste from your `.env`.

Set `PLEX_BOT_DATA_BIND` to the **parent** directory on the host (e.g. `/mnt/user/VmBOX/docker/plex-bot`) — the manifest appends `/data` itself. The directory must be owned by UID 1000 (the in-container `bot` user).

### Local development

```bash
cp .env.example .env
# fill in
docker compose -f docker-compose.dev.yml up --build
```

`./src` is bind-mounted, so source edits are picked up after a container restart.

## Configuration

All configuration is via environment variables. See `.env.example` for the full list with defaults.

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | — | Token from @BotFather |
| `ADMIN_CHAT_ID` | yes | — | Group or DM where approve cards land (see below) |
| `PLEX_TOKEN` | yes | — | Server owner's `X-Plex-Token` |
| `PLEX_SERVER_NAME` | no | auto | Override; otherwise discovered from the API |
| `PLEX_MACHINE_IDENTIFIER` | no | auto | Override; otherwise discovered from the API |
| `OVERSEERR_PUBLIC_URL` | no | — | When unset, the Overseerr button is hidden |
| `OVERSEERR_API_KEY` | conditional | — | Required when `OVERSEERR_PUBLIC_URL` is set |
| `WATCH_URL` | no | `https://app.plex.tv/desktop/` | "Watch in browser" link |
| `DB_PATH` | no | `/data/db.sqlite` | SQLite database location |
| `BOT_LANG` | no | `en` | `en` or `ru` |
| `PROXY_URL` | no | — | e.g. `socks5://192.168.0.1:1080` |
| `NO_PROXY` | no | `localhost,127.0.0.1` | Comma-separated bypass list |
| `HEALTH_PORT` | no | `9095` | Port for `/healthz` and `/metrics` |
| `LOG_LEVEL` | no | `INFO` | Python logging level |
| `DAILY_SYNC_CRON` | no | `0 4 * * *` | Crontab expression for daily reconciliation |
| `SHARED_LIBRARY_IDS` | no | `[]` (= all) | Comma-separated Plex section IDs to share |
| `ALLOW_SYNC` | no | `1` | Plex sharing flag: allow sync |
| `ALLOW_CAMERA_UPLOAD` | no | `0` | Plex sharing flag: allow camera upload |
| `ALLOW_CHANNELS` | no | `0` | Plex sharing flag: allow channels |

### Admin chat: group or DM

`ADMIN_CHAT_ID` accepts both forms:

- **Group**: a chat id starting with `-100…`. The bot must be a member; any participant can approve, reject, manage users, and trigger sync. Useful for shared admin teams.
- **DM**: your personal Telegram user id (positive number). Approve cards and the `/admin` panel land in your private chat with the bot — only you can act on them.

To find either id, message [@userinfobot](https://t.me/userinfobot) in the relevant chat.

## Customization

### Apps screen

The "Get apps" message is loaded from `src/plex_tg_bot/i18n/apps/<lang>.html` (Telegram-flavoured HTML, baked into the image). Edit your fork's file or open a PR.

### Locales

To add a new language, drop a `<lang>.yml` next to `en.yml` and a matching `<lang>.html` next to `apps/en.html`, then set `BOT_LANG=<lang>`. The locale parity test enforces key coverage.

## Architecture

Single asyncio process:

```
aiogram (Telegram long-polling)
  └─ handlers (bot/, services/)
       ├─ aiosqlite  ──────────────────── /data/db.sqlite
       ├─ httpx (Plex API + Overseerr)
       └─ APScheduler (daily sync cron)

aiohttp server (separate task)
  └─ /healthz  /metrics  ──────────────── :9095
```

## FAQ

**Telegram is blocked in my country — how do I configure a proxy?**
Set `PROXY_URL=socks5://...` (or `http://...`). The bot routes Telegram and Plex API traffic through it. `NO_PROXY` bypasses for internal hosts (e.g. your local Plex IP).

**My `ADMIN_CHAT_ID` looks like a positive number — why did it stop working?**
Telegram groups have negative ids (often `-100…`). Personal DMs have positive ids. Verify by messaging @userinfobot in the same chat.

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

## License

MIT — see `LICENSE`.
