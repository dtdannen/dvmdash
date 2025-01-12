
CREATE TABLE dvms (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL CHECK (first_seen <= CURRENT_TIMESTAMP),
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL CHECK (last_seen <= CURRENT_TIMESTAMP),
    last_profile_event_id TEXT DEFAULT NULL,
    last_profile_event_raw_json JSONB DEFAULT NULL,
    last_profile_event_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    deactivated_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,

    CHECK (first_seen <= last_seen)
);


CREATE TABLE dvm_stats_rollups (
    dvm_id TEXT REFERENCES dvms(id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    period_feedback BIGINT NOT NULL CHECK (period_feedback >= 0),
    period_responses BIGINT NOT NULL CHECK (period_responses >= 0),
    running_total_feedback BIGINT NOT NULL,
    running_total_responses BIGINT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dvm_id, timestamp),

    CHECK (period_start <= timestamp),
    CHECK (period_end <= CURRENT_TIMESTAMP),
    CHECK (period_start <= period_end),
    CHECK (running_total_feedback >= period_feedback),
    CHECK (running_total_responses >= period_responses)
);


CREATE TABLE kind_stats_rollups (
    kind INTEGER CHECK (kind BETWEEN 5000 AND 5999),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    period_requests BIGINT NOT NULL CHECK (period_requests >= 0),
    period_responses BIGINT NOT NULL CHECK (period_responses >= 0),
    running_total_requests BIGINT NOT NULL,
    running_total_responses BIGINT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (kind, timestamp),

    CHECK (period_start <= timestamp),
    CHECK (period_end <= CURRENT_TIMESTAMP),
    CHECK (period_start <= period_end),
    CHECK (running_total_requests >= period_requests),
    CHECK (running_total_responses >= period_responses)
);


CREATE TABLE users (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_dvm BOOLEAN NOT NULL DEFAULT FALSE,
    discovered_as_dvm_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (first_seen <= last_seen),
    CHECK (discovered_as_dvm_at >= first_seen)
);

CREATE TABLE kind_dvm_support (
    kind INTEGER CHECK (kind BETWEEN 5000 AND 5999),
    dvm TEXT REFERENCES dvms(id) ON DELETE CASCADE,
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    interaction_type TEXT NOT NULL CHECK (interaction_type IN ('both', 'request_only', 'response_only')),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (kind, dvm),
    CHECK (first_seen <= last_seen)
);

CREATE TABLE time_window_stats (
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,    -- When this stat was computed
    window_size TEXT NOT NULL CHECK (window_size IN ('1 hour', '24 hours', '7 days', '30 days')),
    period_start TIMESTAMP WITH TIME ZONE NOT NULL, -- Start of the period these stats cover
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,   -- End of the period these stats cover
    total_requests INTEGER NOT NULL CHECK (total_requests >= 0),
    total_responses INTEGER NOT NULL CHECK (total_responses >= 0),
    unique_dvms INTEGER NOT NULL CHECK (unique_dvms >= 0),
    unique_kinds INTEGER NOT NULL CHECK (unique_kinds >= 0),
    unique_users INTEGER NOT NULL CHECK (unique_users >= 0),
    popular_dvm TEXT REFERENCES dvms(id),
    popular_kind INTEGER CHECK (popular_kind BETWEEN 5000 AND 5999),
    competitive_kind INTEGER CHECK (competitive_kind BETWEEN 5000 AND 5999),
    PRIMARY KEY (timestamp, window_size),

    CHECK (period_start <= period_end),
    CHECK (period_end <= CURRENT_TIMESTAMP)
);

CREATE TABLE entity_activity (
    id SERIAL PRIMARY KEY, -- Auto-generated unique identifier
    entity_id TEXT NOT NULL, -- either a user npub, dvm npub, or kind integer as text
    entity_type TEXT NOT NULL CHECK (entity_type IN ('dvm', 'user', 'kind')),
    observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    event_id TEXT NOT NULL,
    UNIQUE (entity_id, observed_at, event_id)
);

CREATE TABLE monthly_activity (
    year_month TEXT PRIMARY KEY,
    total_requests INTEGER NOT NULL CHECK (total_requests >= 0),
    total_responses INTEGER NOT NULL CHECK (total_responses >= 0),
    unique_dvms INTEGER NOT NULL CHECK (unique_dvms >= 0),
    unique_kinds INTEGER NOT NULL CHECK (unique_kinds >= 0),
    unique_users INTEGER NOT NULL CHECK (unique_users >= 0),
    dvm_activity JSONB NOT NULL DEFAULT '[]'::jsonb, -- Array of {dvm_id, feedback_count, response_count}
    kind_activity JSONB NOT NULL DEFAULT '[]'::jsonb, -- Array of {kind, request_count, response_count}
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT check_year_month_format CHECK (year_month ~ '^\d{4}-\d{2}$')

);

-- Create an events table to store raw Nostr events
CREATE TABLE raw_events (
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

CREATE TABLE cleanup_log (
    id SERIAL PRIMARY KEY,
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('dvm', 'user')),
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL,
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL,
    deactivated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB -- For storing any additional context about the cleanup
);

CREATE INDEX idx_monthly_activity_year_month ON monthly_activity(year_month DESC);

-- Add indexes for cleanup operations
CREATE INDEX idx_dvms_cleanup ON dvms (last_seen, is_active);
CREATE INDEX idx_cleanup_log_entity ON cleanup_log (entity_type, entity_id);
CREATE INDEX idx_cleanup_log_deleted ON cleanup_log (deleted_at);

-- Create indexes for raw event query patterns
CREATE INDEX IF NOT EXISTS idx_events_kind ON raw_events(kind);
CREATE INDEX IF NOT EXISTS idx_events_pubkey ON raw_events(pubkey);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON raw_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_kind_created_at ON raw_events(kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_pubkey_created_at ON raw_events(pubkey, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_inserted_at ON raw_events(inserted_at DESC);

-- Entity Activity Table Indices
CREATE INDEX idx_entity_activity_timestamp ON entity_activity (observed_at DESC);
CREATE INDEX idx_entity_activity_type_timestamp ON entity_activity (entity_type, observed_at DESC);

-- DVMs Table Indices
CREATE INDEX idx_dvms_last_seen ON dvms (last_seen DESC);
CREATE INDEX idx_dvms_first_seen ON dvms (first_seen);

-- DVM Stats Rollups Indices
CREATE INDEX idx_dvm_stats_dvm_timestamp ON dvm_stats_rollups (dvm_id, timestamp DESC);
CREATE INDEX idx_dvm_stats_timestamp ON dvm_stats_rollups (timestamp DESC);
CREATE INDEX idx_dvm_stats_period_responses ON dvm_stats_rollups (period_responses DESC);
CREATE INDEX idx_dvm_stats_responses_dvm ON dvm_stats_rollups (running_total_responses DESC, dvm_id);

-- Kind Stats Rollups Indices
CREATE INDEX idx_kind_stats_kind_timestamp ON kind_stats_rollups (kind, timestamp DESC);
CREATE INDEX idx_kind_stats_timestamp ON kind_stats_rollups (timestamp DESC);
CREATE INDEX idx_kind_stats_period_requests ON kind_stats_rollups (period_requests DESC);
CREATE INDEX idx_kind_stats_requests_kind ON kind_stats_rollups (running_total_requests DESC, kind);

-- Users Table Indices
CREATE INDEX idx_users_last_seen ON users (last_seen DESC);
CREATE INDEX idx_users_first_seen ON users (first_seen);
CREATE INDEX idx_users_is_dvm ON users (is_dvm) WHERE is_dvm = TRUE;

-- Kind DVM Support Indices
CREATE INDEX idx_kind_dvm_support_kind ON kind_dvm_support (kind, last_seen DESC);
CREATE INDEX idx_kind_dvm_support_dvm ON kind_dvm_support (dvm, last_seen DESC);

-- Time Window Stats Indices
CREATE INDEX idx_time_window_stats_timestamp ON time_window_stats (timestamp DESC);
CREATE INDEX idx_time_window_stats_window ON time_window_stats (window_size, timestamp DESC);
CREATE INDEX idx_time_window_stats_window_timestamp ON time_window_stats (window_size, timestamp DESC);