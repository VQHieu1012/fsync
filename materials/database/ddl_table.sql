CREATE TABLE articles (
    article_id BIGINT PRIMARY KEY,
    source_name TEXT NOT NULL,
    article_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    raw_s3_key TEXT,
    parsed_s3_key TEXT,
    retry_count INT DEFAULT 0,
    discovered_at TIMESTAMP NOT NULL DEFAULT NOW(),
    processing_started_at TIMESTAMP,
    processed_at TIMESTAMP
);

ALTER TABLE articles ADD COLUMN next_retry_at TIMESTAMP;

ALTER TABLE articles ADD COLUMN last_error TEXT;

ALTER TABLE articles ADD COLUMN failed_at TIMESTAMP;

CREATE INDEX idx_articles_status ON articles(status);

CREATE INDEX idx_articles_status_discovered ON articles(status, discovered_at);