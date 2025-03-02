-- Create the dvm_profiles table to store NIP-89 metadata events
CREATE TABLE IF NOT EXISTS dvm_profiles (
    id SERIAL PRIMARY KEY,
    dvm_id TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    content JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Add indexes for efficient querying
    CONSTRAINT fk_dvm FOREIGN KEY (dvm_id) REFERENCES dvms(id) ON DELETE CASCADE
);

-- Add index for faster lookups by DVM ID
CREATE INDEX IF NOT EXISTS idx_dvm_profiles_dvm_id ON dvm_profiles(dvm_id);

-- Add index for faster lookups by creation time
CREATE INDEX IF NOT EXISTS idx_dvm_profiles_created_at ON dvm_profiles(created_at);

-- Add comment to explain the table's purpose
COMMENT ON TABLE dvm_profiles IS 'Stores NIP-89 metadata events (kind 31990) for DVMs';
