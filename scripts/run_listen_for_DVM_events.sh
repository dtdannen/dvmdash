#!/bin/bash

SCRIPT="/home/dvmdash/dvmdash/scripts/listen_for_DVM_events.py"
LOG_DIR="/home/dvmdash/dvmdash/logs"
LOG_FILE="$LOG_DIR/listen_for_DVM_events_output_$(date +"%Y-%m-%d_%H-%M-%S").log"
VENV_PATH="/home/dvmdash/dvmdash/backend_venv"  # Update this with the correct path to your virtual environment
MAX_LOG_FILES=10

# Create the log directory if it doesn't exist
mkdir -p $LOG_DIR

# Set the working directory
cd /home/dvmdash/dvmdash || exit
echo "[$(date)] Working directory set to: $(pwd)"

echo "[$(date)] Checking if script is already running..."
if pgrep -f "$SCRIPT" > /dev/null
then
    echo "[$(date)] Script is already running. Exiting."
    exit 1
fi

echo "[$(date)] Generating random values..."
RUNTIME_LIMIT=$(shuf -i 5-15 -n 1)
LOOKBACK_TIME=$(shuf -i 108-1337 -n 1)
WAIT_LIMIT=$(shuf -i 2-10 -n 1)
WAIT_LIMIT=$((WAIT_LIMIT * 60))

echo "[$(date)] Random values generated: RUNTIME_LIMIT=$RUNTIME_LIMIT, LOOKBACK_TIME=$LOOKBACK_TIME, WAIT_LIMIT=$WAIT_LIMIT"
echo "[$(date)] Activating virtual environment..."


# Activate the virtual environment
if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
else
    echo "[$(date)] Virtual environment activation script not found: $VENV_PATH/bin/activate" >> /home/dvmdash/dvmdash/logs/cron_output.log
    exit 1
fi

# Run the Python script and log the output

echo "[$(date)] Running the Python script..."
python $SCRIPT $RUNTIME_LIMIT $LOOKBACK_TIME $WAIT_LIMIT &> $LOG_FILE

if [ $? -ne 0 ]; then
    echo "[$(date)] Python script encountered an error."
else
    echo "[$(date)] Python script completed successfully."
fi

echo "[$(date)] Deactivating virtual environment..."
deactivate

# Count the number of log files
FILE_COUNT=$(ls -1 $LOG_DIR | wc -l)

# If the number of files is greater than MAX_LOG_FILES, remove the oldest files
if [ "$FILE_COUNT" -gt "$MAX_LOG_FILES" ]; then
    echo "[$(date)] Number of log files ($FILE_COUNT) exceeds $MAX_LOG_FILES. Deleting the oldest files..." >> $LOG_DIR/cleanup.log

    # Find and remove the oldest files, keeping only the newest MAX_LOG_FILES
    ls -1t $LOG_DIR | tail -n +$((MAX_LOG_FILES+1)) | xargs -I {} rm -- "$LOG_DIR/{}"

    echo "[$(date)] Cleanup complete. Removed $((FILE_COUNT - MAX_LOG_FILES)) files." >> $LOG_DIR/cleanup.log
else
    echo "[$(date)] Number of log files ($FILE_COUNT) is within the limit. No action needed." >> $LOG_DIR/cleanup.log
fi