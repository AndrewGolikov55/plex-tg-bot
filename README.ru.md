# plex-tg-bot

[English](README.md) · [Русский](README.ru.md)

Self-hosted Telegram-бот, через который твои друзья запрашивают доступ к Plex-серверу. Один тап админа в личке — и приглашение улетает на email. После принятия бот показывает кнопки на приложения, веб-плеер и Overseerr.

## Скриншоты

<p align="center">
  <img src="docs/screenshots/start-no-access.png" alt="Меню /start у нового пользователя" width="300">
  <img src="docs/screenshots/request-flow.png"   alt="Флоу /request"                     width="300">
  <img src="docs/screenshots/admin-panel.png"    alt="Админ-панель"                      width="300">
</p>

<sub>Свои PNG'и положи в <code>docs/screenshots/</code> — список ожидаемых имён в <code>docs/screenshots/README.md</code>.</sub>

## Возможности

- Открытый флоу `/request` — друг вводит email и пометку «откуда узнал», а админу прилетает карточка с inline-кнопками `[Approve] [Reject]`.
- В один тап approve бот шлёт инвайт через Plex API, доимпортирует юзера в Overseerr и пишет ему DM.
- Inline-панель админа: пагинированный список пользователей с per-row отзывом доступа (Plex API + БД) и confirmation-картой.
- Адаптивное `/start` меню по статусу пользователя (`нет доступа` / `на рассмотрении` / `доступ есть`).
- Ежедневная сверка с Plex (по умолчанию 04:00) — ловит юзеров, которым ты вручную отозвал доступ через Plex Web.
- HTTP / SOCKS прокси для регионов, где Telegram заблокирован.
- i18n: из коробки английский и русский, переключение через `BOT_LANG`.
- `/healthz` и Prometheus `/metrics` для мониторинга.

## Быстрый старт

### Через `docker compose`

```bash
git clone https://github.com/AndrewGolikov55/plex-tg-bot.git
cd plex-tg-bot
cp .env.example .env
# отредактируй .env — минимум TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, PLEX_TOKEN
mkdir -p data
docker compose up -d
docker compose logs -f
```

Бот стартует на порту `9095` с `/healthz` и `/metrics`. SQLite-состояние лежит в `./data/db.sqlite`.

### Portainer (GitOps)

Создай stack, указывающий на этот репо:

- Repository: `https://github.com/AndrewGolikov55/plex-tg-bot.git`
- Compose path: `docker-compose.yml`
- Environment variables: вставь из `.env`.

`PLEX_BOT_DATA_BIND` — это **родительский** каталог на хосте (например, `/mnt/user/VmBOX/docker/plex-bot`); манифест сам приклеит `/data`. Каталог должен принадлежать UID 1000 (внутри контейнера юзер `bot`).

### Локальная разработка

```bash
cp .env.example .env
# заполни
docker compose -f docker-compose.dev.yml up --build
```

`./src` примонтирован bind-mount'ом — правки кода подхватятся после рестарта контейнера.

## Конфигурация

Всё через переменные окружения. Полный список с дефолтами в `.env.example`.

| Переменная | Обязательна | Дефолт | Описание |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | да | — | Токен от @BotFather |
| `ADMIN_CHAT_ID` | да | — | Группа или DM, куда приходят approve-карточки (см. ниже) |
| `PLEX_TOKEN` | да | — | `X-Plex-Token` владельца сервера |
| `PLEX_SERVER_NAME` | нет | auto | Override; иначе автодискавер через API |
| `PLEX_MACHINE_IDENTIFIER` | нет | auto | Override; иначе автодискавер через API |
| `OVERSEERR_PUBLIC_URL` | нет | — | Если не задан — кнопка Overseerr скрывается |
| `OVERSEERR_API_KEY` | условно | — | Обязателен, если задан `OVERSEERR_PUBLIC_URL` |
| `WATCH_URL` | нет | `https://app.plex.tv/desktop/` | Ссылка «Смотреть в браузере» |
| `DB_PATH` | нет | `/data/db.sqlite` | Путь к sqlite |
| `BOT_LANG` | нет | `en` | `en` или `ru` |
| `PROXY_URL` | нет | — | Например `socks5://192.168.0.1:1080` |
| `NO_PROXY` | нет | `localhost,127.0.0.1` | Список хостов в обход прокси |
| `HEALTH_PORT` | нет | `9095` | Порт для `/healthz` и `/metrics` |
| `LOG_LEVEL` | нет | `INFO` | Уровень логирования Python |
| `DAILY_SYNC_CRON` | нет | `0 4 * * *` | Crontab ежедневной сверки |
| `SHARED_LIBRARY_IDS` | нет | `[]` (= все) | Какие библиотеки расшарить (через запятую) |
| `ALLOW_SYNC` | нет | `1` | Plex флаг: разрешить sync |
| `ALLOW_CAMERA_UPLOAD` | нет | `0` | Plex флаг: загрузка с камеры |
| `ALLOW_CHANNELS` | нет | `0` | Plex флаг: каналы |

### Админ-чат: группа или личка

`ADMIN_CHAT_ID` принимает оба формата:

- **Группа**: id вида `-100…`. Бота надо добавить в группу; любой её участник может одобрять/отклонять заявки, удалять юзеров и запускать sync. Удобно для команды админов.
- **Личка (DM)**: твой персональный Telegram user id (положительное число). Approve-карточки и панель `/admin` приходят тебе в личку — только ты можешь нажимать кнопки. Удобно для одиночного оператора.

Чтобы узнать id любого чата — напиши [@userinfobot](https://t.me/userinfobot) в нужный чат, он ответит chat id.

## Кастомизация

### Экран «Скачать приложения»

Сообщение для кнопки «Get apps» подгружается из `src/plex_tg_bot/i18n/apps/<lang>.html` (Telegram-flavour HTML, baked в образ). Редактируй файл в своём форке или открывай PR.

### Локали

Чтобы добавить язык — положи `<lang>.yml` рядом с `en.yml` и `<lang>.html` рядом с `apps/en.html`, выстави `BOT_LANG=<lang>`. Parity-тест на CI следит за совпадением ключей.

## Архитектура

Один asyncio-процесс:

```
aiogram (Telegram long-polling)
  └─ handlers (bot/, services/)
       ├─ aiosqlite  ──────────────────── /data/db.sqlite
       ├─ httpx (Plex API + Overseerr)
       └─ APScheduler (cron ежедневной сверки)

aiohttp сервер (отдельная корутина)
  └─ /healthz  /metrics  ──────────────── :9095
```

## FAQ

**Telegram заблокирован у провайдера — как настроить прокси?**
Поставь `PROXY_URL=socks5://...` (или `http://...`). Бот пустит через него и Telegram, и Plex API. `NO_PROXY` нужен для локальных хостов (твой Plex по локалке).

**`ADMIN_CHAT_ID` положительный — почему перестало работать?**
У групп Telegram отрицательные id (часто начинаются на `-100`). У личек — положительные. Проверь, написав @userinfobot в нужный чат.

**Бот заапрувил, но юзер видит «no servers available».**
Plex иногда обрабатывает инвайт несколько минут. Попроси юзера подождать и обновить страницу.

## Контрибьютинг

```bash
git clone https://github.com/AndrewGolikov55/plex-tg-bot.git
cd plex-tg-bot
uv venv
uv pip install -e ".[dev]"
uv run pytest
```

PR'ы welcome — добавляй тесты, проверь что `ruff` и `mypy` зелёные.

## Лицензия

MIT — см. `LICENSE`.
