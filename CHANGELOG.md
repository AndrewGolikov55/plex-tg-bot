# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
