# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DVMDash is a monitoring and debugging tool for Data Vending Machine (DVM) activity on Nostr. DVMs (NIP-90) offload computationally expensive tasks from relays and clients in a decentralized manner. This tool collects, processes, and displays statistics about DVM activity across the Nostr network.

**Live Demo**: https://stats.dvmdash.live/

## Architecture

DVMDash is an event-driven microservices pipeline consisting of six main services:

1. **Event Collector** (3 replicas): Connects to Nostr relays and collects DVM-related events (kinds 5xxx-6xxx), storing them in Redis queues. Supports three collection modes: real-time listening, historical data loading (up to 20 days), and monthly historical data from CDN.

2. **Coordinator**: Manages relay assignments for collectors, distributes relays among instances, monitors collector health via heartbeats, and coordinates database cleanup operations.

3. **Batch Processor** (scalable to 5 instances): Consumes events from Redis queue in configurable batches (default: 10,000 events) and stores processed data in PostgreSQL.

4. **API** (FastAPI): Serves processed data with memory-aware TTL caching (60s TTL, 20k item limit). Implements cache warming on startup and continuous refresh every 50 seconds for optimal performance.

5. **Frontend** (Next.js 14): App Router-based React application with client-side and server-side rendering. Uses SWR for data fetching. Main pages: dashboard (`/`), DVM stats (`/dvm-stats`), kind stats (`/kind-stats`).

6. **Admin** (Next.js 14): Separate administrative panel for relay connection management, collector health monitoring, and direct Redis/PostgreSQL access.

**Data Flow Pipeline**:
```
Nostr Relays → Event Collector (3x) → Redis Queue → Batch Processor (up to 5x) → PostgreSQL → API (with cache) → Frontend/Admin
```

## Core Data Model

**Entities**:
- **DVMs**: Nostr pubkeys that respond to NIP-90 requests (5xxx kinds) with responses (6xxx kinds)
- **Kinds**: Nostr event kinds that DVMs support (5000-5999 for requests, 6000-6999 for responses)
- **Users**: Entities that send requests to DVMs
- **Time Windows**: Stats aggregated for 1h, 24h, 7d, and 30d periods

**Key Tables**:
- `dvms`: DVM entities with pubkey, first/last seen, active status, profile metadata
- `users`: User entities with pubkey, is_dvm flag, discovery timestamps
- `kind_dvm_support`: Maps DVMs to supported kinds with interaction type (both/request_only/response_only)
- `entity_activity`: Individual event observations (entity_id, kind, observed_at, event_id) with UNIQUE constraint
- `time_window_stats`: Global statistics by time window (total requests/responses, unique DVMs/kinds/users, popular entities)
- `dvm_time_window_stats`: Per-DVM statistics by time window
- `kind_time_window_stats`: Per-kind statistics by time window
- `monthly_activity`: Historical monthly rollups for long-term trend analysis

**Data Retention**:
- Detailed event data: 30-day rolling window
- Monthly summaries: Archived indefinitely
- Automated cleanup managed by Coordinator service

## Shared Backend Module

Located at `/backend/shared`, this module contains common code shared across all Python services to avoid duplication:

- `dvm/`: DVM event kind definitions and configuration (`dvm_kinds.yaml`)
- `models/`: Pydantic models for events (`dvm_event.py`) and graph data (`graph_models.py`)
- `utils/`: Database utilities (`db.py`) and Nostr protocol helpers (`nostr.py`)

All backend services import from this shared module for consistency.

## Development Commands

### Setup and Running

```bash
# Start full application stack
docker compose --profile all up

# Start specific profiles
docker compose --profile core up       # PostgreSQL + Redis only
docker compose --profile collector up  # Event collector
docker compose --profile processor up  # Batch processor
docker compose --profile admin up      # Admin panel

# Check container status and health
docker compose ps

# View logs (use -f to follow)
docker compose logs -f api
docker compose logs -f event_collector
docker compose logs -f batch_processor
docker compose logs -f coordinator

# Restart specific service
docker compose restart api
```

### Database and Redis Access

```bash
# Access PostgreSQL (credentials: devuser/devpass, database: dvmdash_pipeline)
docker compose exec postgres_pipeline psql -U devuser -d dvmdash_pipeline

# Inspect Redis data
docker compose exec redis redis-cli
docker compose exec redis redis-cli LLEN dvmdash_events  # Check queue length
docker compose exec redis redis-cli KEYS '*'              # List all keys
```

### Frontend Development

```bash
# Build and lint
cd frontend/dvmdash-frontend
npm install
npm run build
npm run lint

# Run locally outside Docker (requires .env.local with NEXT_PUBLIC_API_URL=http://localhost:8000)
npm run dev
```

### Admin Panel

```bash
# Build and run admin panel (accessible at http://localhost:3002)
cd dvmdash  # Start from root
docker build -t admin-container ./admin
docker run -p 3002:3000 --env-file ./admin/.env.production admin-container

# Navigate to http://localhost:3002/admin/relays to manage relay connections
```

### Production Deployment

```bash
# Set required environment variables
export DO_TOKEN="your-digitalocean-token"
export DO_PROJECT_ID="your-project-id"
export BETTERSTACK_TOKEN="your-betterstack-token"

# Run deployment script (deploys to DigitalOcean App Platform)
cd deploy
python production_deploy.py
```

## Configuration

All services are configured via environment variables in `docker-compose.yml`:

**Event Collector**:
- `LOAD_HISTORICAL_DATA=false` - Load historical data on startup
- `HISTORICAL_MONTHS=2` - Months of historical data to load
- `START_LISTENING=true` - Begin real-time event listening
- `DAYS_LOOKBACK=20` - Days of history to request from relays
- `REDIS_URL=redis://redis:6379/0`
- `LOG_LEVEL=INFO`
- `NOSTR_LOG_LEVEL=OFF` - Nostr SDK log level

**Coordinator**:
- `RELAY_DISTRIBUTION_INTERVAL_SECONDS=30` - Relay redistribution frequency
- `HEALTH_CHECK_INTERVAL_SECONDS=60` - Collector health check frequency
- `COLLECTOR_TIMEOUT_SECONDS=300` - Timeout before marking collector as dead
- `DAILY_CLEANUP_INTERVAL_SECONDS=15` - Cleanup interval (86400 in production)

**Batch Processor**:
- `BATCH_SIZE=10000` - Events per batch
- `MAX_WAIT_SECONDS=3` - Max time to wait for batch to fill
- `BACKTEST_MODE=true` - Testing mode without live relays

**API**:
- `DEFAULT_RELAYS=wss://relay.damus.io,...` - Relay list
- `ENVIRONMENT=development`
- `LOG_LEVEL=INFO`

**Frontend**:
- `NEXT_PUBLIC_API_URL=http://localhost:8000` - Client-side API URL
- `NEXT_PUBLIC_METADATA_API_URL=http://api:8000` - Server-side API URL (for SSR)
- `NEXT_PUBLIC_LOG_LEVEL=INFO`

## Architectural Patterns

**Event-Driven Pipeline**: Decoupled services communicate via Redis queues, enabling high-throughput event processing and easy horizontal scaling of individual components.

**Time Window Statistics**: Pre-computed statistics for four time windows (1h, 24h, 7d, 30d) enable efficient querying and caching. Rolling window cleanup manages data size.

**Relay Coordination**: The coordinator dynamically distributes relays among collectors, allowing optimization without service restart. Collectors report heartbeats for health monitoring.

**Memory-Aware Caching**: API uses TTLCache with explicit memory tracking and eviction policies to prevent OOM. Cache warming on startup and continuous background refresh (every 50 seconds) ensure optimal performance.

**Health Check Pattern**: All services implement Docker health checks. The coordinator monitors collector heartbeats. Services auto-restart on failure with exponential backoff.

## Debugging

**No data in frontend**:
```bash
docker compose logs event_collector          # Check relay connections
docker compose exec redis redis-cli LLEN dvmdash_events  # Verify queue has events
docker compose logs batch_processor          # Check processing status
```

**Slow API responses**:
- Check cache statistics at `/api/cache/stats`
- Verify cache warming is functioning in API logs
- Check database indexes if queries are slow

**Event collectors not connecting**:
```bash
docker compose logs coordinator              # Verify coordinator is healthy
docker compose exec redis redis-cli KEYS '*relay*'  # Check relay configuration
```

**Frontend errors on startup**:
- Wait for events to arrive from relays (may take a few minutes initially)
- Frontend auto-updates when data becomes available
- Verify API is accessible at http://localhost:8000

**Admin panel relay management**:
- Navigate to http://localhost:3002/admin/relays
- View active relay connections and collector status
- Switch environments via `REDIS_URL` env variable