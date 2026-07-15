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
    record_type TEXT NOT NULL,
    unique_hash TEXT NOT NULL,
    data_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
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
