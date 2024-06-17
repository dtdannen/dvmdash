# Scripts

## run_and_monitor_listener.sh

First, make sure you set up the `backend_venv`

```commandline
cd dvmdash/  # top level of the project
python3.10 -m venv backend_venv  # this name is used by the .sh script
source backend_venv/bin/activate
pip install -r requirements_backend.txt
```


### How to run this script once

Use this script to collect DVM related events from relays.

```commandline
cd dvmdash/  # top level of the project
source backend_venv/bin/activate
python scripts/listen_for_DVM_events.py 2 200 10
```

### How to test script for chron job works:

```commandline
cd dvmdash/  # top level of the project
chmod +x run_listen_for_DVM_events.sh
./run_listen_for_DVM_events.sh
```

then you can watch the log file by running this in another terminal (make sure to find your log file, which will have a different date):
```commandline
tail -f logs/listen_for_DVM_events_output_2024-05-18_19-35-36.log
```

### How to set it up as a chron job:

Make sure you made the script executable via `chmod +x run_listen_for_DVM_events.sh`

```commandline
crontab -e
```

Add this line to the crontab file:

```commandline
*/5 * * * * /path/to/run_listen_for_DVM_events.sh
```

## Stat docs

For faster rendering of general stats and metrics, we will compute stats for each dvm, user,
kind, and network. The network stats page is any information that's not per user, dvm, or
kind. For example, the total number of kinds seens, total number of DVMs, etc.

### DVM
Stats to compute per DVM
    
- number of responses (jobs finished)
- number of requests to other kinds
- number of feedback events
- number of invoices paid
- total amount of invoices requested
- total amount of invoices paid
- average response time
- fastest response time
- slowest response time
- average amount of invoices requested
- how often it responds

### User
Stats to compute per User

- number of job requests
- most popular type of job
- average amount paid per DVM
- total amount paid for DVMs

### Kind
Stats to computer per Kind

- How many DVMs have ever responded
- Average response from the DVMs


### Network
Stats to computer for the whole network




