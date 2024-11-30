#!/bin/bash

# Create test data directory if it doesn't exist
mkdir -p /app/backend/event_collector/test_data

# If using test data and the source file exists, copy it
if [ "$USE_TEST_DATA" = "true" ] && [ -f /test_data/dvmdash.prod_events_29NOV2024.json ]; then
    echo "Copying test data file..."
    cp /test_data/dvmdash.prod_events_29NOV2024.json /app/backend/event_collector/test_data/
    echo "Test data file copied successfully"
fi

# Run the main application with appropriate flags
if [ "$USE_TEST_DATA" = "true" ]; then
    python -m src.main --test-data --batch-size $TEST_DATA_BATCH_SIZE --batch-delay $TEST_DATA_BATCH_DELAY
else
    python -m src.main
fi