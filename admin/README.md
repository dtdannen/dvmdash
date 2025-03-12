# DVMDash Admin Container

This container provides a standalone admin interface for managing DVMDash. It allows you to perform administrative tasks without needing to expose the main API to the internet or implement complex authentication.

## Features

- **Relay Management**: Add, remove, and configure relays
- **System Status**: Monitor event collectors and their status
- **Debug Tools**: View Redis state for debugging

## Getting Started

### Local Development

1. Install dependencies:
   ```bash
   cd admin
   npm install
   ```

2. Create a `.env.local` file with the following content:
   ```
   REDIS_URL=redis://localhost:6379/0
   POSTGRES_USER=devuser
   POSTGRES_PASSWORD=devpass
   POSTGRES_DB=dvmdash_pipeline
   POSTGRES_HOST=localhost
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```

4. Open [http://localhost:3000](http://localhost:3000) in your browser.

### Using Docker Compose

1. Start the admin container along with Redis and Postgres:
   ```bash
   docker-compose --profile admin up
   ```

2. Open [http://localhost:3001](http://localhost:3001) in your browser.

### Connecting to Production

You can run the admin container locally and connect it to your production Redis and Postgres instances:

```bash
docker run -p 3001:3000 \
  -e REDIS_URL=redis://your-production-redis:6379/0 \
  -e POSTGRES_USER=prod_user \
  -e POSTGRES_PASSWORD=prod_pass \
  -e POSTGRES_DB=dvmdash_pipeline \
  -e POSTGRES_HOST=your-production-db \
  dvmdash-admin
```

or if you have a local .env.production file:

```bash
docker build -t admin-container ./admin
docker run -p 3002:3000 --env-file ./admin/.env.production admin-container
```

This allows you to manage your production environment without exposing admin endpoints to the internet.

## Architecture

The admin container is a standalone Next.js application that directly interacts with Redis and Postgres. It does not depend on the main DVMDash API, which means:

1. You can run it independently of the rest of the system
2. It reduces the attack surface by not exposing admin endpoints in the main API
3. You can connect it to any environment by providing the appropriate Redis and Postgres connection details

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `POSTGRES_USER` | Postgres username | `devuser` |
| `POSTGRES_PASSWORD` | Postgres password | `devpass` |
| `POSTGRES_DB` | Postgres database name | `dvmdash_pipeline` |
| `POSTGRES_HOST` | Postgres host | `postgres_pipeline` |
