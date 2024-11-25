-- Create an events table to store raw Nostr events
CREATE TABLE IF NOT EXISTS raw_events (
    id TEXT PRIMARY KEY,                    -- Nostr event id
    pubkey TEXT NOT NULL,                   -- Event creator's public key
    created_at TIMESTAMP NOT NULL,          -- Event creation timestamp
    kind INTEGER NOT NULL,                  -- Nostr event kind
    content TEXT,                           -- Event content
    sig TEXT,                               -- Event signature
    tags JSONB,                             -- Event tags as JSONB
    raw_data JSONB NOT NULL,                -- Complete raw event data
    inserted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,  -- Record insertion timestamp
    -- Indexes for common query patterns
    CONSTRAINT valid_kind CHECK (kind >= 0)
);

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_events_kind ON raw_events(kind);
CREATE INDEX IF NOT EXISTS idx_events_pubkey ON raw_events(pubkey);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON raw_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_kind_created_at ON raw_events(kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_pubkey_created_at ON raw_events(pubkey, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_inserted_at ON raw_events(inserted_at DESC);