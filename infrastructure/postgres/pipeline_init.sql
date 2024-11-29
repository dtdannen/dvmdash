-- infrastructure/postgres/pipeline_init.sql

CREATE TABLE global_stats_rollups (
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL CHECK (timestamp <= CURRENT_TIMESTAMP),
	period_start TIMESTAMP WITH TIME ZONE NOT NULL CHECK (period_start <= CURRENT_TIMESTAMP),
    period_requests INTEGER NOT NULL CHECK (period_requests >= 0),
	period_responses INTEGER NOT NULL CHECK (period_responses >= 0),
	running_total_requests BIGINT NOT NULL,
    running_total_responses BIGINT NOT NULL,
	running_total_unique_dvms BIGINT NOT NULL,
	running_total_unique_kinds BIGINT NOT NULL,
	running_total_unique_users BIGINT NOT NULL,
	most_popular_dvm TEXT REFERENCES dvms(id),
	most_popular_kind INTEGER REFERENCES kinds(id),
    PRIMARY KEY (timestamp),

    CHECK (period_start <= timestamp),
    CHECK (running_total_requests >= period_requests),
    CHECK (running_total_responses >= period_responses)
);

CREATE TABLE dvms (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL CHECK (first_seen <= CURRENT_TIMESTAMP),
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL CHECK (last_seen <= CURRENT_TIMESTAMP),
	last_profile_event_id TEXT DEFAULT NULL,
    last_profile_event_raw_json JSONB DEFAULT NULL,
	last_profile_event_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,

    CHECK (first_seen <= last_seen)
);

CREATE TABLE kinds (
    id INTEGER PRIMARY KEY,
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL CHECK (first_seen <= CURRENT_TIMESTAMP),
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL CHECK (last_seen <= CURRENT_TIMESTAMP),

    CHECK (first_seen <= last_seen)
);

CREATE TABLE dvm_stats_rollups (
    dvm_id TEXT REFERENCES dvms(id),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_feedback BIGINT NOT NULL CHECK (period_feedback >= 0),
	period_responses BIGINT NOT NULL CHECK (period_responses >= 0),
    running_total_feedback BIGINT NOT NULL,
    running_total_responses BIGINT NOT NULL,
    PRIMARY KEY (dvm_id, timestamp),

    CHECK (period_start <= timestamp),
    CHECK (running_total_feedback >= period_feedback),
    CHECK (running_total_responses >= period_responses)
);

CREATE TABLE kind_stats_rollups (
    kind INTEGER REFERENCES kinds(id),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_requests BIGINT NOT NULL CHECK (period_requests >= 0),
    period_responses BIGINT NOT NULL CHECK (period_responses >= 0),
    running_total_requests BIGINT NOT NULL,
    running_total_responses BIGINT NOT NULL,
    PRIMARY KEY (kind, timestamp),

    CHECK (period_start <= timestamp),
    CHECK (running_total_requests >= period_requests),
    CHECK (running_total_responses >= period_responses)
);

CREATE TABLE users (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
	is_dvm BOOLEAN NOT NULL DEFAULT FALSE,
	discovered_as_dvm_at TIMESTAMP WITH TIME ZONE,

    CHECK (first_seen <= last_seen),
    CHECK (discovered_as_dvm_at >= first_seen)
);

CREATE TABLE kind_dvm_support (
    kind_id INTEGER REFERENCES kinds(id),
    dvm_id TEXT REFERENCES dvms(id),
    first_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    interaction_type TEXT NOT NULL CHECK (interaction_type IN ('both', 'request_only', 'response_only')),
    PRIMARY KEY (kind_id, dvm_id),
    CHECK (first_seen <= last_seen)
);

-- Global Stats Rollups Indices
CREATE INDEX idx_global_stats_timestamp ON global_stats_rollups (timestamp DESC);
CREATE INDEX idx_global_stats_period ON global_stats_rollups (period_start DESC);

-- DVMs Table Indices
CREATE INDEX idx_dvms_last_seen ON dvms (last_seen DESC);
CREATE INDEX idx_dvms_first_seen ON dvms (first_seen);

-- Kinds Table Indices
CREATE INDEX idx_kinds_last_seen ON kinds (last_seen DESC);
CREATE INDEX idx_kinds_first_seen ON kinds (first_seen);

-- DVM Stats Rollups Indices
CREATE INDEX idx_dvm_stats_dvm_timestamp ON dvm_stats_rollups (dvm_id, timestamp DESC);
CREATE INDEX idx_dvm_stats_timestamp ON dvm_stats_rollups (timestamp DESC);
CREATE INDEX idx_dvm_stats_period_responses ON dvm_stats_rollups (period_responses DESC);
-- Index for finding most popular DVM
CREATE INDEX idx_dvm_stats_responses_dvm ON dvm_stats_rollups (running_total_responses DESC, dvm_id);

-- Kind Stats Rollups Indices
CREATE INDEX idx_kind_stats_kind_timestamp ON kind_stats_rollups (kind, timestamp DESC);
CREATE INDEX idx_kind_stats_timestamp ON kind_stats_rollups (timestamp DESC);
CREATE INDEX idx_kind_stats_period_requests ON kind_stats_rollups (period_requests DESC);
-- Index for finding most popular kind
CREATE INDEX idx_kind_stats_requests_kind ON kind_stats_rollups (running_total_requests DESC, kind);

-- Users Table Indices
CREATE INDEX idx_users_last_seen ON users (last_seen DESC);
CREATE INDEX idx_users_first_seen ON users (first_seen);
CREATE INDEX idx_users_is_dvm ON users (is_dvm) WHERE is_dvm = TRUE;

-- For finding all DVMs that support a specific kind
CREATE INDEX idx_kind_dvm_support_kind ON kind_dvm_support (kind_id, last_seen DESC);

-- For finding all kinds that a specific DVM supports
CREATE INDEX idx_kind_dvm_support_dvm ON kind_dvm_support (dvm_id, last_seen DESC);