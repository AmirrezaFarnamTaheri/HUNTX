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
    FOREIGN KEY (source_observation_id)
        REFERENCES seen_files(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS record_verdicts (
    unique_hash TEXT NOT NULL,
    record_type TEXT NOT NULL,
    syntax_status TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    probe_status TEXT NOT NULL DEFAULT 'unknown',
    probe_checked_at REAL,
    probe_expires_at REAL,
    policy_status TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    policy_tier TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL DEFAULT '[]',
    updated_at REAL NOT NULL,
    PRIMARY KEY (unique_hash, record_type, policy_tier)
);

CREATE TABLE IF NOT EXISTS published_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_name TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    published_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS publication_intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_key TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    generation TEXT NOT NULL,
    created_at REAL NOT NULL,
    completed_at REAL,
    UNIQUE(publication_key, artifact_hash, generation),
    CHECK(length(artifact_hash) = 64)
);

CREATE TABLE IF NOT EXISTS publication_deliveries (
    intent_id INTEGER NOT NULL,
    destination_id TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'desired',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at REAL,
    confirmed_at REAL,
    remote_receipt TEXT,
    error_class TEXT,
    PRIMARY KEY (intent_id, destination_id),
    FOREIGN KEY (intent_id) REFERENCES publication_intents(id) ON DELETE CASCADE,
    CHECK(state IN ('desired', 'sending', 'confirmed', 'failed', 'unknown_outcome', 'skipped')),
    CHECK(attempt_count >= 0)
);

CREATE TABLE IF NOT EXISTS telegram_bot_updates (
    token_fingerprint TEXT NOT NULL,
    update_id INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    received_at REAL NOT NULL,
    PRIMARY KEY (token_fingerprint, update_id),
    CHECK(length(token_fingerprint) = 64)
);

CREATE TABLE IF NOT EXISTS telegram_bot_consumers (
    token_fingerprint TEXT NOT NULL,
    consumer_id TEXT NOT NULL,
    acknowledged_update_id INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    updated_at REAL NOT NULL,
    PRIMARY KEY (token_fingerprint, consumer_id),
    CHECK(length(token_fingerprint) = 64),
    CHECK(acknowledged_update_id >= 0),
    CHECK(active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS bot_users (
    user_id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
    username TEXT,
    registered_at REAL NOT NULL,
    approved INTEGER NOT NULL DEFAULT 0,
    muted INTEGER DEFAULT 0,
    last_delivered_at REAL DEFAULT 0,
    default_format TEXT DEFAULT 'npvt'
);

CREATE TABLE IF NOT EXISTS bot_delivery_checkpoint (
    user_id TEXT PRIMARY KEY,
    attempted INTEGER NOT NULL DEFAULT 0,
    sent INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES bot_users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bot_delivery_items (
    user_id TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    artifact_name TEXT NOT NULL,
    delivered_at REAL NOT NULL,
    PRIMARY KEY (user_id, artifact_hash),
    FOREIGN KEY (user_id) REFERENCES bot_users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ingestion_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anchor_ts INTEGER NOT NULL,
    target_start_ts INTEGER NOT NULL,
    window_seconds INTEGER NOT NULL DEFAULT 3600,
    status TEXT NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE(anchor_ts, target_start_ts, window_seconds)
);

CREATE TABLE IF NOT EXISTS ingestion_work_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    window_start_ts INTEGER NOT NULL,
    window_end_ts INTEGER NOT NULL,
    continuation_cursor INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_token TEXT,
    lease_expires_at INTEGER,
    next_retry_at INTEGER,
    last_error TEXT,
    items_ingested INTEGER NOT NULL DEFAULT 0,
    bytes_ingested INTEGER NOT NULL DEFAULT 0,
    rotation_seq INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    completed_at INTEGER,
    FOREIGN KEY (campaign_id) REFERENCES ingestion_campaigns(id) ON DELETE CASCADE,
    UNIQUE(source_id, window_start_ts, window_end_ts)
);

CREATE INDEX IF NOT EXISTS idx_records_type ON records(record_type);
CREATE INDEX IF NOT EXISTS idx_records_unique ON records(unique_hash);
CREATE INDEX IF NOT EXISTS idx_records_hash ON records(source_file_hash);
CREATE INDEX IF NOT EXISTS idx_records_build
    ON records(record_type, is_active, source_file_hash, unique_hash, id);
CREATE INDEX IF NOT EXISTS idx_record_verdicts_eligibility
    ON record_verdicts(record_type, policy_tier, syntax_status, policy_status, probe_status, probe_expires_at);
CREATE INDEX IF NOT EXISTS idx_pub_route ON published_artifacts(route_name, artifact_hash);
CREATE INDEX IF NOT EXISTS idx_published_route_latest
    ON published_artifacts(route_name, published_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_publication_deliveries_state
    ON publication_deliveries(state, last_attempt_at);
CREATE INDEX IF NOT EXISTS idx_telegram_bot_updates_received
    ON telegram_bot_updates(token_fingerprint, received_at);
CREATE INDEX IF NOT EXISTS idx_telegram_bot_consumers_watermark
    ON telegram_bot_consumers(token_fingerprint, active, acknowledged_update_id);
CREATE INDEX IF NOT EXISTS idx_bot_delivery_items_user_time
    ON bot_delivery_items(user_id, delivered_at DESC);
CREATE INDEX IF NOT EXISTS idx_seen_files_hash ON seen_files(raw_hash);
CREATE INDEX IF NOT EXISTS idx_seen_files_status ON seen_files(status);
CREATE INDEX IF NOT EXISTS idx_seen_files_pending ON seen_files(status, id);
CREATE INDEX IF NOT EXISTS idx_seen_files_source_hash ON seen_files(source_id, raw_hash, id);
CREATE INDEX IF NOT EXISTS idx_source_lifecycle_trust ON source_lifecycle(trust_state);
CREATE INDEX IF NOT EXISTS idx_ingestion_work_lifo
    ON ingestion_work_items(status, window_end_ts DESC, rotation_seq ASC, id ASC);
CREATE INDEX IF NOT EXISTS idx_ingestion_work_lease
    ON ingestion_work_items(status, lease_expires_at, next_retry_at);
CREATE INDEX IF NOT EXISTS idx_ingestion_work_source
    ON ingestion_work_items(source_id, window_start_ts, window_end_ts);
