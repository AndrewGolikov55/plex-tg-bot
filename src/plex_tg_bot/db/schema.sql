PRAGMA journal_mode=WAL;

-- Anyone who ever pressed /start
CREATE TABLE IF NOT EXISTS users (
  telegram_id   INTEGER PRIMARY KEY,
  username      TEXT,
  display_name  TEXT,
  language      TEXT NOT NULL DEFAULT 'ru',
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL
);

-- Each /request submission is one row
CREATE TABLE IF NOT EXISTS requests (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_id   INTEGER NOT NULL REFERENCES users(telegram_id),
  email         TEXT NOT NULL,
  referrer      TEXT NOT NULL,
  status        TEXT NOT NULL,
  admin_chat_id INTEGER,
  admin_msg_id  INTEGER,
  decided_by    INTEGER,
  decided_at    INTEGER,
  reject_reason TEXT,
  created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_tg ON requests(telegram_id);

-- Source of truth for "do you have access?"
CREATE TABLE IF NOT EXISTS shared_users (
  email             TEXT PRIMARY KEY,
  telegram_id       INTEGER,
  plex_user_id      INTEGER,
  status            TEXT NOT NULL,
  shared_at         INTEGER NOT NULL,
  revoked_at        INTEGER,
  last_seen_in_plex INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shared_status ON shared_users(status);

-- Cached server identity (auto-discovered from plex.tv resources)
CREATE TABLE IF NOT EXISTS plex_server_cache (
  id                 INTEGER PRIMARY KEY CHECK(id=1),
  machine_identifier TEXT NOT NULL,
  friendly_name      TEXT NOT NULL,
  refreshed_at       INTEGER NOT NULL
);
