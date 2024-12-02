# Introduction

DVMDash aims to be a monitoring and debugging tool for DVM activity on Nostr. Data Vending Machines (nip-90) offload computationally expensive tasks from relays and clients in a decentralized, free-market manner. They are especially useful for AI tools, algorithmic processing of user’s feeds, and many other use cases.

A kind is a numeric id that represents a type of job. This is a loose categorization that is not strictly enforced, but
emergent. Anyone runs a DVM can choose which Kind(s) they support, and users can submit jobs on any Kind.

There are multiple use cases for DVMDash

## Use Case 1: Global Network Metrics, Stats, and Plots

This part of the system listens for Nostr DVM json events from relays and funnels them through a near real-time
data pipeline to compute metrics and stats about the whole network, as well as specific DVMs and Kinds. It contains the
following components:

A. Asyncio Python Program to grab events from relays and put into a queue
B. Redis Queue storing json events
C. ETCD as a lock for batch processing (D)
D. Python batch processing to compute latest metrics by:
	- grab a batch of events from the queue
	- grab the latest stats from Postgres rollups
	- compute new total metrics by iterating over all events in batch
	- write batch of events to mongo event collection (E)
	- write new rollup to mongo rollup collection (F)
E. Mongo collection of all events ever received
	- For posterity and to recompute metrics in case of failure, and to allow looking up of individual events later
	- writes:
		- batch writes of new events. if not new, then ignored
	- reads:
		- lookup of single documents by event id
		- lookup N most recent documents, filtered by different fields (i.e. find the 10 most recent kind 5300 events)
F. Postgres table of rollups
	- to make it easy to quickly get the most recent metrics for all events
	- tables:
		1. unique users id list
		2. unique dvm ids list (with column for current profile, and when profile was last updated)
		3. DVM stats table that contains columns for
			1. dvm id
			2. dvm name
			3. number of job requests
			4. average response time
			5. total sats earned
			6. dvm profile description (nip-89 announcements)
		4. Kind stats table that contains columns for:
			1. kind number
			2. total jobs requested
			3. total jobs responded
			4. total sats paid
			5. number of dvms that support this job
		5. KIND+DVM Table - used to track how many DVMs support a kind, and how many (and which) kinds a certain DVM supports
			1. each row has two foreign keys, and a value here means that a specific DVM supports a specific kind
		6. global stats table which has columns for:
			1. number of dvm job requests
			2. number of dvm job results
			3. number of unique dvm users (this is the count of table 1 above)
			4. number of unique dvms (count from table 2 above)
			5. current most popular dvm
			6. current most paid dvm
			7. current most popular kind
			8. current most paid kind
			9. total sats earned across the whole dvm ecosystem


## File structure for the project:

dvmdash/
├── README.md
├── docker-compose.yml
├── infrastructure/
│   ├── etcd/
│   │   ├── Dockerfile
│   │   └── config/
│   │       ├── dev.yaml      # Local development config
│   │       └── prod.yaml     # Production config with DO hostnames
│   └── postgres/
│       ├── pipeline_init.sql
│       └── events_init.sql
├── backend/
│   ├── event_collector/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   │       ├── main.py
│   │       └── config.py
│   ├── batch_processor/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   │       ├── main.py
│   │       └── config.py
│   ├── graph_processor/          # Future Neo4j processing component
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/
│   │       ├── main.py
│   │       └── config.py
│   ├── shared/
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── dvm_event.py
│   │   │   └── graph_models.py
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── db.py
│   │       └── nostr.py
│   └── tests/
│       ├── unit/
│       └── integration/
├── frontend/
│   ├── next.config.js
│   ├── package.json
│   ├── tsconfig.json
│   ├── public/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx
│   │   │   ├── layout.tsx
│   │   │   ├── metrics/        # Metrics dashboard pages
│   │   │   │   ├── page.tsx
│   │   │   │   └── [...slug]/
│   │   │   └── debug/         # Debug tool pages
│   │   │       ├── page.tsx
│   │   │       └── graph/
│   │   ├── components/
│   │   │   ├── metrics/
│   │   │   │   ├── StatCard.tsx
│   │   │   │   └── TimeSeriesChart.tsx
│   │   │   └── debug/
│   │   │       ├── GraphViewer.tsx
│   │   │       └── EventInspector.tsx
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   └── types.ts
│   │   └── styles/
│   └── tests/
│       ├── unit/
│       └── e2e/
├── api/                        # API service layer
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── main.py
│       ├── routes/
│       │   ├── metrics.py
│       │   └── graph.py
│       └── services/
│           ├── metrics.py
│           └── graph.py
├── docs/
│   ├── architecture.md
│   ├── metrics-pipeline.md
│   └── api-spec.md
└── scripts/
    ├── setup-dev.sh
    └── deploy.sh


## Deployment Plan:

Droplet 1 (Web/API):
- Frontend
- API Service
- Nginx

Droplet 2 (Queue/Lock):
- ETCD (for locks)
- Redis

Droplet 3+ (Event Collectors):
- Event Collector 1
- Event Collector 2
- Event Collector N
(each collecting from different relay sets, putting events into queue)

Droplet 4+ (Batch):
- Batch Processor 1
- Batch Processor 2
- Batch Processor N
(each grabbing events from queue, using ETCD for locking, writing to DBs)

Droplet 5 (Data):
- MongoDB (stores all raw events)

Droplet 6 (Data):
- PostgreSQL (stores rollups/stats)

The plan will be for each droplet to have it's own docker-compose.yml file (or dockerfile if there's only one)


## Questions we want to be able to answer from data

This is the motivation behind the database schema.

Note: This schema could be way more complicated. It's intentionally mostly about answering high level, global statements
about DVMs, Kinds, and the entire ecosystem, to enable fast tracking and general high level stats.

Questions:
1. How many DVM job requests have been submitted? (Postgres)
	- answered by global stats table
2. How many DVM job results have been returned? (Postgres)
	- answered by global stats table
3. How many unique users are there? (Postgres)
	- answered by users table
4. What's the most popular DVM? (Postgres, dvm stats table)
	- answered by looking up the last rollup for the mentioned DVM
5. How much money is each DVM earning? (NEO4J)
6. Does a DVM appear to be down? 
   - answered by tracking how many job requests this DVM has ignored
7. When was the last time a DVM completed a task?
8. Have any DVMs failed to deliver after accepting payment? 
   - Did they refund that payment?
9. How long, on average, does it take this DVM to respond? (NEO4J)
	- 
10. For Task X, what's the average amount of time it takes for a DVM to complete a task?
11. Which DVMs are competing with my DVM?


12. What was the root cause of my DVM to fail? (NEO4J) 
13. Which DVM in a DVM chain failed? (NEO4J)
14. Can I easily string the output of DVM A into my new DVM B to create a chain? (Documentation)
15. What are the design patterns of creating multi-DVM workflows? (Documentation)
16. How can I create a loop of DVMs? (Documentation)
17. How can I create backup DVMs to run in the event of failure? (Documentation, Examples)
18. How can I build reliable workflows of DVMs to power my app? (Documentation, Examples)
19. Can I be notified when my DVM fails; runs out of money; or some other condition occurs? (Documentation, Examples)
20. I want to build a DVM but I don’t know what to do, where should I start? (Documentation)

Questions for later:

21. Which relays are used for DVM events? (Separate tool that is yet to be developed)


### Easy, Medium, and Hard metrics

Trivial metrics are simple counts that can be easily computed each rollup. These include:
- total job requests ✅ 
- total job responses ✅ 

Easy metrics require simple queries over data:
- total job requests per Kind ✅ 	
- total job results per Kind ✅ 
- total job results per DVM ✅ 
- most popular DVM ✅ 
- most popular Kind ✅ 

Medium metrics are those that require tracking sets of unique ids. They require counting items in a table where the items are restricted to being unique in their ID fields:
- number of unique users ✅ 
- number of unique DVMs ✅ 
- number of unique Kinds ✅ 
- number of unique DVMs per Kind ✅ 
- number of Kinds a DVM supports ✅
- most competitive Kind ✅

Hard metrics are those that require computing stats between multiple events:
- how many sats a DVM earned (requires tracking if a job was finished)
- how many sats were earned globally
- how many sats were earned per Kind
- average response time of a DVM
- average response time of a Kind
- fastest DVM per Kind
- top earning DVM per Kind

## Postgres pipeline schema

### Database Tables

Global stats table that will show all the front page metrics:

```sql
CREATE TABLE global_stats_rollups (
    timestamp TIMESTAMP WITH TIME ZONE,
	period_start TIMESTAMP WITH TIME ZONE,
    period_requests INTEGER,
	period_responses INTEGER,
	running_total_requests BIGINT,
    running_total_responses BIGINT,
	running_total_unique_dvms BIGINT,
	running_total_unique_kinds BIGINT,
	running_total_unique_users BIGINT,
	most_popular_dvm TEXT REFERENCES dvms(id),
	most_popular_kind INTEGER REFERENCES kinds(id),
    PRIMARY KEY (timestamp)
);
```

Table tracking DVMs:

```sql
CREATE TABLE dvms (
    id TEXT PRIMARY KEY,
    name TEXT,
    first_seen TIMESTAMP WITH TIME ZONE,
	last_seen TIMESTAMP WITH TIME ZONE,
	last_profile_event_id TEXT DEFAULT NULL,
	last_profile_event_updated_at TIMESTAMP WITH TIME ZONE
);
```

Table tracking Kinds:

```sql
CREATE TABLE kinds (
    id INTEGER PRIMARY KEY,
    first_seen TIMESTAMP WITH TIME ZONE,
	last_seen TIMESTAMP WITH TIME ZONE,
);
```

Table tracking DVM Rollups:

```sql
CREATE TABLE dvm_stats_rollups (
    dvm_id TEXT REFERENCES dvms(id),
    timestamp TIMESTAMP WITH TIME ZONE,
    period_feedback BIGINT,
	period_responses BIGINT,
    running_total_feedback BIGINT,
    running_total_responses BIGINT,
    PRIMARY KEY (dvm_id, timestamp)
);
```

Table tracking Kind Rollups:

```sql
CREATE TABLE kind_stats_rollups (
    kind INTEGER REFERENCES kinds(id),
    timestamp TIMESTAMP WITH TIME ZONE,
    period_requests BIGINT,
    period_responses BIGINT,
    running_total_requests BIGINT,
    running_total_responses BIGINT,
    PRIMARY KEY (kind, timestamp)
);
```

Table tracking Users:

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
	last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
	is_dvm BOOLEAN DEFAULT FALSE,
	discovered_as_dvm_at TIMESTAMP WITH TIME ZONE,
);
```

### Description of how we will generate each metric

1. **period job requests**
   - the batch processor will count the number of kind 5000-5999 events in the batch
2. **running total requests**
  - the batch processor will add the period_requests to the most recent global rollup
3. **period job results**
   - the batch processor will count the number of kind 6000-6999 events in the batch
4. **running total results**
	- the batch processor will add the period_results to the most recent global rollup
5. **running_total_unique_dvms**
	- the batch processor will query the dvms table for the COUNT(*)
6. **running_total_unique_kinds**
	- the batch processor will query the kinds table for the COUNT(*)
7. **running_total_unique_users**
	- the batch processor will query the users table for the COUNT(*)
8. **most_popular_dvm**
	- the batch processor will query the dvm_stats_rollups table for the dvm with the most period_results
9. **most_popular_kind**
	- the batch processor will query the kind_stats_rollups table for the kind with the most period_requests
10. **number_of_unique_dvms_per_kind**:
	- batch processor will query the kind_dvm table, grouping by Kind
11. **number_of_kinds_a_dvm_supports**:
	- batch processor will query the kind_dvm table, grouping by DVM


### Description of how we will generate plots:

1. Any plot over running totals from global stats rollup table, which gives us::
   - requests over time
   - responses over time
   - unique users over time
   - unique dvms over time
   - unique kinds over time

```sql
WITH params AS (
  SELECT 
    CASE 
      WHEN :time_range = '24h' THEN '15 minutes'
      WHEN :time_range = '7d' THEN '1 hour'
      WHEN :time_range = '30d' THEN '4 hours'
      WHEN :time_range = '90d' THEN '1 day'
      ELSE '1 hour'
    END AS bucket_size
),
time_buckets AS ( 
  SELECT 
    date_trunc('hour', timestamp) AS bucket_time,
    -- Take the last value in each bucket for running totals
    LAST_VALUE(running_total_requests) OVER (
      PARTITION BY date_trunc('hour', timestamp)
      ORDER BY timestamp
      RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) as running_total_requests,
    LAST_VALUE(running_total_responses) OVER (
      PARTITION BY date_trunc('hour', timestamp)
      ORDER BY timestamp
      RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) as running_total_responses,
    LAST_VALUE(running_total_unique_users) OVER (
      PARTITION BY date_trunc('hour', timestamp)
      ORDER BY timestamp
      RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) as running_total_unique_users
  FROM global_stats_rollups
  WHERE timestamp >= NOW() - INTERVAL '7 days'
)
SELECT DISTINCT
  bucket_time as timestamp,
  running_total_requests,
  running_total_responses,
  running_total_unique_users
FROM time_buckets
ORDER BY bucket_time ASC;
```

2. Plot showing number of DVMs per Kind over time

	This query shows the number of active DVMs within the time window.

```sql
WITH params AS (
  SELECT 
    CASE 
      WHEN :time_range = '24h' THEN '15 minutes'
      WHEN :time_range = '7d' THEN '1 hour'
      WHEN :time_range = '30d' THEN '4 hours'
      WHEN :time_range = '90d' THEN '1 day'
      ELSE '1 hour'
    END AS bucket_size
),
active_dvms AS (
  -- First get all DVMs that have been active within our time window
  SELECT d.id, d.last_seen
  FROM dvms d
  WHERE d.last_seen >= NOW() - 
    CASE :time_range
      WHEN '24h' THEN INTERVAL '24 hours'
      WHEN '7d' THEN INTERVAL '7 days'
      WHEN '30d' THEN INTERVAL '30 days'
      WHEN '90d' THEN INTERVAL '90 days'
      ELSE INTERVAL '7 days'
    END
),
kind_activity AS (
  -- Look at kind_stats_rollups to see which DVMs were processing this kind
  SELECT DISTINCT
    date_trunc((SELECT bucket_size FROM params), k.timestamp) AS bucket_time,
    COUNT(DISTINCT d.id) as dvm_count
  FROM kind_stats_rollups k
  JOIN active_dvms d ON k.period_responses > 0  -- Only count DVMs that actually processed requests
  WHERE 
    k.kind = :specific_kind_id
    AND k.timestamp >= NOW() - 
      CASE :time_range
        WHEN '24h' THEN INTERVAL '24 hours'
        WHEN '7d' THEN INTERVAL '7 days'
        WHEN '30d' THEN INTERVAL '30 days'
        WHEN '90d' THEN INTERVAL '90 days'
        ELSE INTERVAL '7 days'
      END
    AND k.timestamp <= d.last_seen  -- Only count DVMs up until their last seen time
  GROUP BY 
    date_trunc((SELECT bucket_size FROM params), k.timestamp)
)
SELECT 
  bucket_time as timestamp,
  COALESCE(dvm_count, 0) as dvm_count
FROM kind_activity
ORDER BY bucket_time ASC;
```

while this query shows the total number of dvms to ever have supported this kind:

```sql
WITH params AS (
  SELECT 
    CASE 
      WHEN :time_range = '24h' THEN '15 minutes'
      WHEN :time_range = '7d' THEN '1 hour'
      WHEN :time_range = '30d' THEN '4 hours'
      WHEN :time_range = '90d' THEN '1 day'
      ELSE '1 hour'
    END AS bucket_size
),
historical_dvms AS (
  -- Count all unique DVMs that have ever processed this kind up to each timestamp
  SELECT 
    date_trunc((SELECT bucket_size FROM params), k.timestamp) AS bucket_time,
    COUNT(DISTINCT dvm_id) as total_historical_dvms
  FROM (
    -- For each timestamp, we want to consider all DVMs that processed this kind at any point up to that time
    SELECT DISTINCT k2.timestamp, k1.dvm_id
    FROM kind_stats_rollups k1
    CROSS JOIN (
      SELECT DISTINCT timestamp 
      FROM kind_stats_rollups 
      WHERE kind = :specific_kind_id
      AND timestamp >= NOW() - 
        CASE :time_range
          WHEN '24h' THEN INTERVAL '24 hours'
          WHEN '7d' THEN INTERVAL '7 days'
          WHEN '30d' THEN INTERVAL '30 days'
          WHEN '90d' THEN INTERVAL '90 days'
          ELSE INTERVAL '7 days'
        END
    ) k2
    WHERE k1.kind = :specific_kind_id
    AND k1.period_responses > 0
    AND k1.timestamp <= k2.timestamp
  ) k
  GROUP BY date_trunc((SELECT bucket_size FROM params), k.timestamp)
)
SELECT 
  bucket_time as timestamp,
  total_historical_dvms
FROM historical_dvms
ORDER BY bucket_time ASC;
```

and then to combine both of them (which we will probably do in practice)

```sql
WITH params AS (
  -- ... same params CTE as before ...
),
active_dvms AS (
  -- ... same active_dvms query from previous example ...
),
historical_dvms AS (
  -- ... historical_dvms query from above ...
)
SELECT 
  COALESCE(a.bucket_time, h.bucket_time) as timestamp,
  COALESCE(a.dvm_count, 0) as dvm_count,
  COALESCE(h.total_historical_dvms, 0) as total_historical_dvms
FROM active_dvms a
FULL OUTER JOIN historical_dvms h ON a.bucket_time = h.bucket_time
ORDER BY timestamp ASC;
```

3. Plot showing number of feedback and responses per DVM over time

```sql
WITH params AS (
  SELECT 
    CASE 
      WHEN :time_range = '24h' THEN '15 minutes'
      WHEN :time_range = '7d' THEN '1 hour'
      WHEN :time_range = '30d' THEN '4 hours'
      WHEN :time_range = '90d' THEN '1 day'
      ELSE '1 hour'
    END AS bucket_size
),
time_buckets AS (
  SELECT 
    date_trunc((SELECT bucket_size FROM params), timestamp) AS bucket_time,
    -- Take the last value in each bucket for running totals
    LAST_VALUE(running_total_feedback) OVER (
      PARTITION BY date_trunc((SELECT bucket_size FROM params), timestamp)
      ORDER BY timestamp
      RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) as running_total_feedback,
    LAST_VALUE(running_total_responses) OVER (
      PARTITION BY date_trunc((SELECT bucket_size FROM params), timestamp)
      ORDER BY timestamp
      RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) as running_total_responses,
    -- Also get the period values for rate of change
    SUM(period_feedback) OVER (
      PARTITION BY date_trunc((SELECT bucket_size FROM params), timestamp)
    ) as period_feedback,
    SUM(period_responses) OVER (
      PARTITION BY date_trunc((SELECT bucket_size FROM params), timestamp)
    ) as period_responses
  FROM dvm_stats_rollups
  WHERE 
    dvm_id = :specific_dvm_id
    AND timestamp >= NOW() - 
      CASE :time_range
        WHEN '24h' THEN INTERVAL '24 hours'
        WHEN '7d' THEN INTERVAL '7 days'
        WHEN '30d' THEN INTERVAL '30 days'
        WHEN '90d' THEN INTERVAL '90 days'
        ELSE INTERVAL '7 days'
      END
)
SELECT DISTINCT
  bucket_time as timestamp,
  running_total_feedback,
  running_total_responses,
  period_feedback,
  period_responses
FROM time_buckets
ORDER BY bucket_time ASC;
```

### How data moves through the database in batch processor

Here's the high-level flow of how data moves through the system:
Step 1: Get and Analyze Raw Events

Pull batch of events from Redis queue
Analyze events to compute period stats:

Count requests/responses
Track DVM activities
Track user activities
Track kind usage


Store all this in BatchStats object

Step 2: Base Table Updates (in transaction)

Update dvms table with new DVMs and their timestamps
Update users table with new users and their timestamps
Update kind_dvm_support table to track which DVMs support which kinds

Step 3: Rollup Table Updates (same transaction)

Update dvm_stats_rollups with per-DVM metrics (responses, feedback)
Update kind_stats_rollups with per-Kind metrics (requests, responses)
Update global_stats_rollups with system-wide running totals

Step 4: Time Window Stats Update (same transaction)

Calculate metrics for each time window (1h, 24h, 7d, 30d, all time)
Update time_window_stats with:

Most popular DVM per window
Most popular Kind per window
Most competitive Kind per window
Total counts for window



Step 5: Event Backup

Save raw events to events database for historical record
This happens outside the main transaction

Each step builds on the previous ones, and steps 2-4 happen in a single transaction to maintain consistency. The base tables track raw data, the rollup tables track running totals (for plots), and the time window stats track current popularity metrics.


## Problems to be solved later

1. Old, duplicate events being submitted. Someone could fudge the numbers of a DVM by submitted old events. The events would have to be older than the redis cache. By default, I think I'm just going to make it so the database queries fail if this happens, and when we get these failures, we can build a process that filters out the bad events and puts the new ones back on the stack. So worst case, if someone tries this, it will just cause errors, rather than bad data and bad stats.