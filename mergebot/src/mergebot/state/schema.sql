CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    last_check_ts DATETIME,
    state_json TEXT
);

CREATE TABLE IF NOT EXISTS seen_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    external_id TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    file_size INTEGER,
    filename TEXT, -- Added
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

CREATE INDEX IF NOT EXISTS idx_records_type ON records(record_type);
CREATE INDEX IF NOT EXISTS idx_records_unique ON records(unique_hash);

CREATE TABLE IF NOT EXISTS published_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_name TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    published_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_pub_route ON published_artifacts(route_name, artifact_hash);
