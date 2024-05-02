#!/bin/bash

script_path="/path/to/your_script.py"
log_file="/path/to/your_script.log"

trap 'echo "Keyboard interrupt received. Exiting..."; exit 0' INT

while true; do
    echo "Starting script at $(date)" >> "$log_file"
    python "$script_path" >> "$log_file" 2>&1

    if [ $? -eq 0 ]; then
        echo "Script completed successfully at $(date)" >> "$log_file"
    else
        echo "Script died at $(date). Restarting in 5 seconds..." >> "$log_file"
        sleep 5
    fi
done