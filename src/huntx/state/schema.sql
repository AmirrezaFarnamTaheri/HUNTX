CREATE TABLE IF NOT EXISTS source_state (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    state_json TEXT,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS source_lifecycle (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    trust_state TEXT NOT NULL DEFAULT 'candidate',
    last_attempt_at REAL,
    last_transport_success_at REAL,
    last_nonempty_at REAL,
    last_valid_at REAL,
    last_published_at REAL,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_error_code TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS seen_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    external_id TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    file_size INTEGER,
    filename TEXT,
    metadata_json TEXT,
    status TEXT DEFAULT 'pending',
    error_msg TEXT,
    UNIQUE(source_id, external_id)
);

CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file_hash TEXT NOT NULL,
    source_observation_id INTEGER,
    record_type TEXT NOT NULL,
    unique_hash TEXT NOT NULL,
    data_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (source_observation_id) REFERENCES seen_files(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS telegram_bot_consumers (
    token_fingerprint TEXT NOT NULL,
    consumer_id TEXT NOT NULL,
    acknowledged_update_id INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    updated_at REAL NOT NULL,
    PRIMARY KEY (token_fingerprint, consumer_id),
    CHECK(length(token_fingerprint) = 64)
);

CREATE INDEX IF NOT EXISTS idx_telegram_bot_consumers_watermark
    ON telegram_bot_consumers(token_fingerprint, active, acknowledged_update_id);

CREATE TABLE IF NOT EXISTS telegram_bot_updates (
    token_fingerprint TEXT NOT NULL,
    update_id INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    received_at REAL NOT NULL,
    PRIMARY KEY (token_fingerprint, update_id),
    CHECK(length(token_fingerprint) = 64)
);

CREATE INDEX IF NOT EXISTS idx_telegram_bot_updates_received
    ON telegram_bot_updates(token_fingerprint, received_at);
