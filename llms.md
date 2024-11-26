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
B. Celery Queue storing json events
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
- Redis (for Celery)
- Celery Worker

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
1. How many DVM job requests have been submitted? (Postgres, global stats table)
2. How many DVM job results have been returned? (Postgres, global stats table)
3. How many unique users are there? (Postgres, users table)
4. What's the most popular DVM? (Postgres, dvm stats table)
5. How much money is each DVM earning? (Postgres, dvm stats table)
6. Does a DVM appear to be down? 
7. When was the last time a DVM completed a task?
8. Have any DVMs failed to deliver after accepting payment? 
   - Did they refund that payment?
9. How long, on average, does it take this DVM to respond?
10. For Task X, what's the average amount of time it takes for a DVM to complete a task?
13. Which DVMs are competing with my DVM? 
11. What was the root cause of my DVM to fail? (NEO4J) 
12. Which DVM in a DVM chain failed? (NEO4J)
14. Can I easily string the output of DVM A into my new DVM B to create a chain? (Documentation)
15. What are the design patterns of creating multi-DVM workflows? (Documentation)
16. How can I create a loop of DVMs? (Documentation)
17. How can I create backup DVMs to run in the event of failure? (Documentation, Examples)
18. How can I build reliable workflows of DVMs to power my app? (Documentation, Examples)
19. Can I be notified when my DVM fails; runs out of money; or some other condition occurs? (Documentation, Examples)
20. I want to build a DVM but I don’t know what to do, where should I start? (Documentation)

Questions for later:

21. Which relays are used for DVM events? (Separate tool that is yet to be developed)



## Metric computation and rationale

-- Global stats fields and their computation policies:

1. timestamp: TIMESTAMP WITH TIME ZONE
   Policy: Simply current timestamp when creating new rollup
   Storage: Direct field in global_stats

2. job_requests: INTEGER
   Policy: Add new request count to previous total
   Storage: Running total in global_stats
   Example: current_total + diff.job_requests

3. job_results: INTEGER
   Policy: Add new result count to previous total
   Storage: Running total in global_stats
   Example: current_total + diff.job_results

4. unique_users: INTEGER
   Policy: Compute at time of rollup from users table. Will store as a snapshot value from this moment in time.
   Storage: users table maintains the source of truth
   Query: SELECT COUNT(*) FROM users
   Rationale: Denormalized count would likely become incorrect over time