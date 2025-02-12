# Production Deployment

This directory contains scripts for deploying the DVMDash application to production on Digital Ocean.

## Prerequisites

The following environment variables must be set:

- `DO_TOKEN`: Digital Ocean API token with write access
- `DO_PROJECT_ID`: Digital Ocean project ID where resources will be created
- `PROJECT_NAME`: (Optional) Name prefix for all resources (default: "dvmdash-prod")
- `BETTERSTACK_TOKEN`: BetterStack API token for log management

## Deployment Process

The deployment is handled in three stages:

### Stage 1: Database Provisioning

- Provisions PostgreSQL database (db-s-6vcpu-16gb)
  - Initializes with pipeline schema
  - Configures networking and security
- Provisions Redis database (db-s-6vcpu-16gb)
  - Configures for high availability
  - Sets up proper memory policies

### Stage 2: Backend Services

- Deploys Event Collector
  - Initially configured to use test data
  - Pulls historical data from CDN
- Deploys Batch Processor
  - Starts with 1 instance
  - Scales to 5 instances for optimal performance
- Deploys Monthly Archiver
  - Configures cleanup intervals
  - Sets up proper database connections

### Stage 3: Frontend & API

- Deploys API Service
  - Configures database connections
  - Sets up proper routing
- Deploys Frontend
  - Builds and deploys Next.js application
  - Configures API endpoint
- Updates Event Collector
  - Switches from test data to live relay data
  - Configures production relay connections

## Usage

```bash
# Make sure environment variables are set
export DO_TOKEN="your-do-token"
export DO_PROJECT_ID="your-project-id"
export BETTERSTACK_TOKEN="your-betterstack-token"

# Run deployment script
python production_deploy.py
```

## Monitoring

- All services are configured with BetterStack logging
- Each service has health checks configured
- Metrics are collected for:
  - Redis queue size
  - Database event counts
  - Processing rates

## Cleanup

The deployment script includes proper cleanup procedures in case of failures. Resources are cleaned up in reverse order of creation to maintain data integrity.

## Components

- `production_deploy.py`: Main deployment orchestration script
- `production_components.py`: Individual service deployment implementations

## Error Handling

- Each stage has proper error handling and cleanup
- Failed deployments trigger automatic cleanup of created resources
- Detailed logging of all operations and errors

## Notes

- The deployment process is designed to be idempotent
- Each stage validates the success of previous stages
- Services are deployed with proper dependencies and wait conditions
- Environment variables are properly secured using DO App Platform secrets
