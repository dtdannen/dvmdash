-- infrastructure/postgres/pipeline_init.sql

-- Users table (unchanged)
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- DVMs table (unchanged)
CREATE TABLE dvms (
    id TEXT PRIMARY KEY,
    name TEXT,
    profile TEXT,
    last_profile_update TIMESTAMP WITH TIME ZONE,
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- DVM stats table (unchanged)
CREATE TABLE dvm_stats (
    dvm_id TEXT REFERENCES dvms(id),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    total_job_requests INTEGER DEFAULT 0,
    avg_response_time INTERVAL,
    total_sats_earned BIGINT DEFAULT 0,
    CONSTRAINT positive_sats CHECK (total_sats_earned >= 0),
    PRIMARY KEY (dvm_id, timestamp)
);

-- Kind stats table (added UNIQUE constraint on kind)
CREATE TABLE kind_stats (
    kind INTEGER,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    total_jobs_requested INTEGER DEFAULT 0,
    total_jobs_responded INTEGER DEFAULT 0,
    total_sats_paid BIGINT DEFAULT 0,
    supporting_dvms INTEGER DEFAULT 0,
    CONSTRAINT positive_jobs CHECK (total_jobs_requested >= 0),
    CONSTRAINT positive_responses CHECK (total_jobs_responded >= 0),
    CONSTRAINT positive_paid CHECK (total_sats_paid >= 0),
    PRIMARY KEY (kind, timestamp),
    UNIQUE (kind)  -- Added this line to allow referencing just the 'kind' column
);

-- Rest of the file remains the same
CREATE TABLE kind_dvm_support (
    kind INTEGER REFERENCES kind_stats(kind),
    dvm_id TEXT REFERENCES dvms(id),
    PRIMARY KEY (kind, dvm_id)
);

-- Global stats table (unchanged)
CREATE TABLE global_stats (
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    job_requests INTEGER DEFAULT 0,
    job_results INTEGER DEFAULT 0,
    unique_users INTEGER DEFAULT 0,
    unique_dvms INTEGER DEFAULT 0,
    most_popular_dvm TEXT REFERENCES dvms(id),
    most_paid_dvm TEXT REFERENCES dvms(id),
    most_popular_kind INTEGER,
    most_paid_kind INTEGER,
    total_sats_earned BIGINT DEFAULT 0,
    CONSTRAINT positive_global_sats CHECK (total_sats_earned >= 0),
    PRIMARY KEY (timestamp)
);

-- Indexes remain unchanged
CREATE INDEX idx_dvm_stats_sats ON dvm_stats(total_sats_earned DESC);
CREATE INDEX idx_kind_stats_jobs ON kind_stats(total_jobs_requested DESC);
CREATE INDEX idx_kind_stats_sats ON kind_stats(total_sats_paid DESC);

CREATE INDEX idx_dvm_stats_time ON dvm_stats(timestamp DESC);
CREATE INDEX idx_kind_stats_time ON kind_stats(timestamp DESC);
CREATE INDEX idx_global_stats_time ON global_stats(timestamp DESC);

CREATE INDEX idx_dvm_stats_dvm_time ON dvm_stats(dvm_id, timestamp DESC);
CREATE INDEX idx_kind_stats_kind_time ON kind_stats(kind, timestamp DESC);