# Scripts

## run_and_monitor_listener.sh

### How to run this script once

Use this script to collect DVM related events from relays. This should be left running, like for example:

```commandline
cd dvmdash/  # top level of the project
python3.10 -m venv backend_venv  # this name is used by the .sh script
chmod +x scripts/run_listen_for_DVM_events.sh
```

### How to set it up as a chron job:

```commandline
crontab -e
```

Add this line to the crontab file:

```commandline
*/5 * * * * /path/to/run_listen_for_DVM_events.sh
```

