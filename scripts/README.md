# Scripts


## make sure you can pull from the repo

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/<your_ssh_key_for_github_here>
```

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

The plan will be to have a new database collection called 'stats', and each DVM, User, and Kind get their own stat page.
There will be a single network stat page. DVM's will be indexed by their npub, User's will be indexed by their npub,
kind stat pages will be indexed by their kind number.

All stats will be computed continuously via a script. The script will load all events from the database, run linearly over
all the events, computing many running stats. Then any additional stats needing to be computed (like averages) will 
happen after the linear processing of all events. Then these values will get saved (updated) to existing stat pages
in the database. 

We should keep a timestamp somewhere so we know how long this is taking. Maybe we can make a stats page for dvmdash for
meta information. We could store all timestamps for finished stat page jobs, the length, how many events were processed.
This info could be shown on the dvmdash About page. Then on any page, we can say how long ago the stats were updated.

This stats collection page computation should probably be concurrent using threads or processes.

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
- last 10 events it interacted with
- last 10 responses

### User
Stats to compute per User

- number of job requests
- most popular type of job
- average amount paid per DVM
- total amount paid for DVMs

### Kind
Stats to computer per Kind

- How many DVMs have ever responded
- Average response time from the DVMs
- Fastest DVM on average to respond
- How much DVMs are charging
- Recent failures to respond (i.e. when a payment was taken, but then no response ever given)


### Network
Stats to computer for the whole network




