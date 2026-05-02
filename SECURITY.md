# Security Policy

## Reporting a Vulnerability

If you find a security issue in this project, please **do not** open a public GitHub issue. Instead, email the maintainer at the address listed in the repo profile, or open a private security advisory via GitHub:

https://github.com/AndrewGolikov55/plex-tg-bot/security/advisories/new

We aim to acknowledge reports within 7 days and provide a remediation plan within 30 days.

## Scope

This project handles two sensitive credentials:

- `TELEGRAM_BOT_TOKEN` — full control over the bot's identity.
- `PLEX_TOKEN` — full account access to the Plex server.

Vulnerabilities of interest include:

- Token leakage via logs, errors, or HTTP responses
- Path traversal or arbitrary file read via `APPS_MARKDOWN_PATH`
- SQL injection in `db/repo.py`
- Authorization bypass in `/admin` (e.g. someone outside `ADMIN_CHAT_ID` triggering admin commands)
- DoS via unbounded resource consumption

Out of scope:

- Issues in upstream dependencies (please report to them directly)
- Misconfiguration of the deploy environment (proxy, firewall, etc.)
