# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.5] - 2026-05-04

### Fixed
- Daily sync was silently doing nothing in production. Plex deprecated `GET /api/v2/shared_servers` (now returns HTTP 405), so `list_shared` always treated the response as a transient failure and exited with `(0, 0)`. Switched to `GET /api/v2/friends?includeSharedServers=1`, walking each friend's `sharedServers` array and filtering by our machine_identifier. The 6 list_shared respx tests rewritten with the new endpoint and payload shape.
- `list_shared` now skips entries with `deletedAt` or `leftAt` set (revoked or voluntarily-left shares). Previously these were surfaced as still-active.

### Added
- `list_shared` returns a new `invite_token` field per row (Plex's per-share token used to construct the accept URL `https://app.plex.tv/desktop/#!/sharing-invite?inviteToken=<...>`). v0.4.0 will surface this in the post-approve DM so users get a one-click accept link in the bot. The field is `None` for shares Plex didn't expose a token for (e.g. legacy invites).

### Internal
- Bumped per-request timeout for `list_shared` to 60s — `includeSharedServers=1` makes the response heavy and the default 30s timed out for accounts with many friends.

## [0.3.4] - 2026-05-04

### Fixed
- `/healthz` no longer returns 503 when the bot is just idle. Previously the endpoint flagged "stale" if no Telegram Update arrived within 600s, which falsely flapped Docker health and Alertmanager every ~10 minutes during quiet periods. The endpoint is now liveness-only — if the asyncio loop and aiohttp server can answer, status is `ok`. The `plexbot_telegram_last_update_ts` gauge stays in `/metrics` and in the JSON body for visibility, but does not gate the response code.

### Internal
- Dropped the `_STALE_S` constant from `http_server.py` and renamed `test_healthz_stale_returns_503` → `test_healthz_ok_even_when_idle`.

## [0.3.3] - 2026-05-03

### Changed
- Apps screen content expanded with per-platform detail: Apple TV, Samsung Tizen, LG webOS, Android TV / Google TV, Roku, Fire TV. Free alternatives called out explicitly — browser at `app.plex.tv`, Kodi + PlexKodiConnect, plus paid options (Plex Pass, Infuse).
- `/help` removed from the slash-commands menu (the `/` button next to the input field). The slash handler stays — typing `/help` still works — but it's no longer advertised since `/start` covers discovery.

### Internal
- Dropped unused `commands.help` i18n key (en/ru).

## [0.3.2] - 2026-05-03

### Changed
- Dropped the `ℹ️ Help` button from the main menu. `/help` is already discoverable via the slash-commands menu (the `/` button next to the input field) since v0.3.0, so the inline button was duplicate UX.
- Bot description (the greeting on an empty chat above the Start button) no longer mentions the GitHub URL.

### Internal
- Dropped the now-unused `menu.help` i18n key and the `help:show` callback handler in `bot/help.py`. The `/help` slash command itself stays.

## [0.3.1] - 2026-05-03

### Fixed
- `[🗑 Remove]` in the admin panel always failed with "Plex unreachable" because Plex returns HTTP 405 on `DELETE /api/v2/shared_servers/{id}`. Switched to `DELETE /api/v2/friends/{plex_user_id}` (the same endpoint python-plexapi uses for `removeFriend`). Sourced `plex_user_id` directly from the local DB row, which removes a redundant `list_shared` round-trip.
- Plex 401 (invalid token) during revoke now surfaces a distinct user-facing message ("Plex token rejected (401). Check PLEX_TOKEN.") instead of the generic "Plex unreachable".

### Internal
- `PlexClient.revoke_share()` signature changed: `(plex_user_id: int)` instead of `(machine_identifier, email)`. Pre-flight `list_shared` lookup gone. Tests rewritten to mock the new endpoint.
- New i18n key `admin.remove_plex_auth_error` (en/ru).

## [0.3.0] - 2026-05-03

### Added
- Bot description and short description — visible on the empty chat above the Start button. Localized for en/ru.
- Slash-commands menu (the `/` button next to the input field). Default scope: `/start`, `/request`, `/help`. Admin chat scope additionally includes `/admin`. Localized command descriptions.
- New `bot/profile.py` module + `setup_bot_profile()` called once at startup. Failures are logged, not fatal.

### Internal
- New i18n keys: `bot_meta.description`, `bot_meta.short_description`, `commands.{start,request,help,admin}`.

## [0.2.0] - 2026-05-03

### Added
- Inline-button admin panel: `/admin` → `[👥 Users] [⏳ Pending] [🔄 Sync]`. Users page is paginated (10/page), shows status emoji per row, and offers a `[🗑]` Remove button per user.
- Per-user remove flow: confirm card → atomic Plex API revoke → DB delete + best-effort DM "access revoked" to the user. On Plex failure nothing is mutated; a retry button is shown.
- `PlexClient.revoke_share()` and `Repo.count_shared_users() / list_shared_users_paginated() / delete_shared_user()`.
- Apps screen content baked into the image as `src/plex_tg_bot/i18n/apps/<lang>.html` (Telegram-flavoured HTML). Fail-fast on missing locale at startup.
- Routing-contract tests cover all dynamic admin callbacks (`admin:menu`, `admin:users:*`, `admin:pending:*`, `admin:sync`).

### Changed
- `/admin` now opens the inline panel; the legacy `/admin list|pending|sync` text sub-commands are removed.
- Apps content is rendered with `parse_mode="HTML"` (was `Markdown`, which Telegram never properly rendered).
- README clarifies that `ADMIN_CHAT_ID` accepts both group and DM ids.

### Fixed
- Crafted `admin:*` callbacks with non-numeric page indices no longer raise `ValueError` — they're silently dismissed.

### Internal
- Drop the `APPS_MARKDOWN_PATH` env var and the bind-mount workflow that came with it.
- `PlexClient.list_shared` now returns the share `id` per row (consumed by `revoke_share`; daily_sync ignores it).
- 17 new admin i18n keys + `notify_user.revoked` mirrored in en/ru. Removed unused `apps.fallback`, `admin.list_header`, `admin.pending_header`.
- `_StubPlex` in routing-contract tests grew a `revoke_share` method to satisfy the protocol.

## [0.1.4] - 2026-05-03

### Added
- Routing-contract tests: every `callback_data` emitted by `build_main_menu` must match a registered handler; every command in `EXPECTED_COMMANDS` must have a `Command(...)` filter. Catches the bug class where a button is wired to a callback with no handler.

## [0.1.3] - 2026-05-03

### Fixed
- "Request access to Plex" inline button (`callback_data=request:start`) now triggers the `/request` flow. Previously the click was silently ignored because no handler was registered for that callback.

## [0.1.2] - 2026-05-03

### Internal
- Release workflow now POSTs to a Portainer GitOps webhook after a successful image push, so each new tag redeploys automatically. The full URL (host + UUID) lives in the `PORTAINER_WEBHOOK` repo secret and is masked from logs.

## [0.1.1] - 2026-05-03

### Fixed
- Bot crashed at startup with `ModuleNotFoundError: aiohttp_socks` when `PROXY_URL` was a `socks5://` URL. Added `aiohttp-socks` as a runtime dependency.
- `PLEX_BOT_DATA_BIND` now expects the **parent** directory; the manifest appends `/data` itself. Simplifies Portainer setup.

### Internal
- Compose manifests moved to repo root: `docker-compose.yml` (production) and `docker-compose.dev.yml` (build from source). Removed `examples/docker-compose.example.yml` duplicate.

## [0.1.0] - 2026-05-02

Initial release.

### Added
- `/start` with adaptive menu by user state (no_access / pending / has_access).
- `/request` FSM: email validation (format + MX) → required referrer → admin card with `[✅ Approve] [❌ Reject]` inline buttons.
- Admin-in-the-loop approve flow with atomic Plex API share + best-effort Overseerr import + DM notify. On Plex error: rollback claim and offer retry.
- Reject flow with optional reason via reply, `/skip`, `/cancel`.
- `/apps` (apps screen), `/watch` (web player URL button), `/overseerr` (URL button when configured), `/help`.
- Daily reconciliation with Plex (cron `0 4 * * *`) — detects users revoked in Plex Web and marks them in the bot DB.
- `/admin list | pending | sync` text-only sub-commands (replaced by inline panel in v0.2.0).
- i18n with `BOT_LANG=ru|en` switchable at runtime.
- HTTP/SOCKS proxy support for Telegram-blocked regions.
- `/healthz` and Prometheus `/metrics` on port 9095.
- SQLite persistence with WAL.
- MIT license, Dockerfile (multi-arch amd64+arm64), GitHub Actions CI + release-to-ghcr.
