# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DVMDash is a monitoring and debugging tool for Data Vending Machine (DVM) activity on Nostr. It collects, processes, and displays statistics about DVM activity across the Nostr network, helping developers understand how DVMs are being used.

## Architecture

DVMDash consists of several microservices that run in Docker containers:

1. **Event Collector**: Connects to Nostr relays and collects DVM-related events, storing them in Redis queues.
2. **Coordinator**: Manages relay assignments for collectors and coordinates activities between components.
3. **Batch Processor**: Processes collected events from Redis queues and stores in PostgreSQL.
4. **API**: FastAPI service that serves processed data with caching for performance.
5. **Frontend**: Next.js application to display DVM statistics.
6. **Admin**: Separate container for administrative functions.

The data flow follows a pipeline pattern:
- Events collected from relays → Redis queue → Batch processor → PostgreSQL database → API → Frontend

## Core Data Model

The system tracks several key entities:
- **DVMs**: Nostr pubkeys that respond to requests with NIP-90 responses
- **Kinds**: Nostr event kinds that DVMs support (5xxx for requests, 6xxx for responses)
- **Users**: Entities that send requests to DVMs
- **Time windows**: Stats are generated for 1h, 24h, 7d, and 30d periods

Data retention uses a tiered strategy:
- Detailed data is kept for a 30-day rolling window
- Monthly summaries are archived for historical data

## Development Environment

### Setup

```bash
# Clone the repository
git clone https://github.com/dtdannen/dvmdash.git
cd dvmdash

# Start the full application stack
docker compose --profile all up

# Or start specific components
docker compose --profile core up      # Database and Redis only
docker compose --profile collector up # Event collector only
docker compose --profile processor up # Batch processor only
```

### Configuration

The system is highly configurable through environment variables in the docker-compose.yml file:

- For the Event Collector:
  - `LOAD_HISTORICAL_DATA`: Set to "true" to load historical data
  - `DAYS_LOOKBACK`: Number of days to request from relays (default: 20)
  
- For the Batch Processor:
  - `BATCH_SIZE`: Number of events to process in each batch (default: 10000)
  - `MAX_WAIT_SECONDS`: Maximum time to wait for events before processing (default: 3)

- For the Frontend:
  - `NEXT_PUBLIC_API_URL`: URL for client-side API calls
  - `NEXT_PUBLIC_METADATA_API_URL`: URL for server-side API calls

### Common Commands

```bash
# Check container status
docker compose ps

# View logs for a specific container
docker compose logs -f api
docker compose logs -f event_collector
docker compose logs -f batch_processor

# Restart a specific container
docker compose restart api

# Access PostgreSQL database
docker compose exec postgres_pipeline psql -U devuser -d dvmdash_pipeline

# Inspect Redis data
docker compose exec redis redis-cli

# Run frontend locally (outside Docker)
cd frontend/dvmdash-frontend
npm install
npm run dev
```

## Database Access

The PostgreSQL database runs on port 5432 with these credentials:
- **User**: devuser
- **Password**: devpass
- **Database**: dvmdash_pipeline

Key tables:
- `dvms`: Information about each DVM
- `kind_dvm_support`: Which kinds each DVM supports
- `entity_activity`: Individual event observations
- `time_window_stats`: Global statistics for different time windows
- `dvm_time_window_stats`: DVM-specific statistics
- `kind_time_window_stats`: Kind-specific statistics

## Deployment

For deployment to production:

```bash
# Export required environment variables
export DO_TOKEN="your-do-token"
export DO_PROJECT_ID="your-project-id"
export BETTERSTACK_TOKEN="your-betterstack-token"

# Run deployment script
cd deploy
python production_deploy.py
```

## Debugging

Common issues and solutions:

1. **No data appearing in frontend**:
   - Check if event collectors are connected to relays: `docker compose logs event_collector`
   - Verify Redis queue has events: `docker compose exec redis redis-cli LLEN dvmdash_events`
   - Check batch processor is running: `docker compose logs batch_processor`

2. **Slow API responses**:
   - The API uses caching to improve performance. Check cache stats at `/api/cache/stats`
   - Database indexes might need optimization if queries are slow

3. **Event collectors not connecting to relays**:
   - Verify coordinator service is running: `docker compose logs coordinator`
   - Check for relay distribution issues in logs
   - Ensure relay URLs are correctly configured in Redis