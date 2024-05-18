#!/bin/bash

SCRIPT="scripts/listen_for_DVM_events.py"
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/listen_for_DVM_events_output_$(date +"%Y-%m-%d_%H-%M-%S").log"
VENV_PATH="backend_venv"

if pgrep -f "$SCRIPT" > /dev/null
then
    echo "Script is already running. Exiting."
    exit 1
fi

RUNTIME_LIMIT=$(shuf -i 5-20 -n 1)
LOOKBACK_TIME=$(shuf -i 108-1337 -n 1)
WAIT_LIMIT=$(shuf -i 2-15 -n 1)
WAIT_LIMIT=$((WAIT_LIMIT * 60))

echo "Running $SCRIPT with RUNTIME_LIMIT=$RUNTIME_LIMIT, LOOKBACK_TIME=$LOOKBACK_TIME, WAIT_LIMIT=$WAIT_LIMIT."

# Activate the virtual environment
source "$VENV_PATH/bin/activate"

python $SCRIPT $RUNTIME_LIMIT $LOOKBACK_TIME $WAIT_LIMIT &> $LOG_FILE

deactivate