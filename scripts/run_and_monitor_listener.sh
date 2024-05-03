#!/bin/bash

script_path="listen_for_DVM_events.py"
log_file="listen_for_DVM_events.log"
virtualenv_path="../venv/"

source "$virtualenv_path/bin/activate"

trap 'echo "Keyboard interrupt received. Exiting..."; deactivate; exit 0' INT

while true; do
    echo "Starting script at $(date)" | tee -a "$log_file"
    python "$script_path"

    if [ $? -eq 0 ]; then
        echo "Script completed successfully at $(date)" | tee -a "$log_file"
    else
        echo "Script died at $(date). Restarting in 5 seconds..." | tee -a "$log_file"
        sleep 5
    fi
done