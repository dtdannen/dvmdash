# dvmdash

DVMDash is a monitoring and debugging tool for DVM activity on Nostr. Data Vending Machines (nip-90) offload computationally expensive tasks from relays and clients in a decentralized, free-market manner. They are especially useful for AI tools, algorithmic processing of user’s feeds, and many other use cases.


A version of the stats app is running here:

https://stats.dvmdash.live/

## Run stats app locally

Install docker compose on your system. Then call docker compose up

```commandline
docker compose --profile all up
```

It takes a minute or two for all the containers to get up and running.

```commandline
docker compose ps
```

Now you should be able to navigate to http://localhost:3000/ and see data from the last 30 days.

## Run the admin panel

This enables managing relay connections without having to restart the whole system.

```bash
cd dvmdash/  # start from the root dir
docker build -t admin-container ./admin
docker run -p 3002:3000 --env-file ./admin/.env.production admin-container
```

Then navigate to http://localhost:3002/admin/relays to see the status of all relays and event collectors. It may take a few seconds to pull the necessary data from redis. You can switch between local and production environments by changing the redis URL that you use, via the `REDIS_URL` env variable.

https://dvmdashbucket.nyc3.cdn.digitaloceanspaces.com/screenshots/admin_panel_event_collectors.png

https://dvmdashbucket.nyc3.cdn.digitaloceanspaces.com/screenshots/admin_panel_relay_connections.png

### Frontend API Configuration

The frontend application uses environment variables to determine API endpoints:

- `NEXT_PUBLIC_API_URL`: Used for client-side API calls from the browser
- `NEXT_PUBLIC_METADATA_API_URL`: Used for server-side API calls during SSR

#### When using Docker Compose
- Environment variables are automatically set in the docker-compose.yml file
- No additional configuration is needed

#### Running Frontend Locally (Outside Docker)
If you want to run the frontend outside of Docker but still connect to the containerized API:

1. Create a `.env.local` file in the `frontend/dvmdash-frontend` directory with:
   ```
   NEXT_PUBLIC_API_URL=http://localhost:8000
   ```
2. Run the frontend with:
   ```
   cd frontend/dvmdash-frontend
   npm install
   npm run dev
   ```

#### Production Deployment
When deploying to production with separate containers:

- Set `NEXT_PUBLIC_API_URL` to your public API endpoint
- Set `NEXT_PUBLIC_METADATA_API_URL` to the internal API endpoint if needed


By default, it's set to continuously pull dvm events from relays over the last 20 days (although many relays don't keep the events that long, so you may just see data from the last day or two). If you want to use historical data from last month and the current month, set `LOAD_HISTORICAL_DATA=true` in the `docker-compose.yml` file under the section `event_collector`. Once it's done pulling historical data, it will start listening to relays for more recent events. Keep in mind this requires a few GB of data. The historical data available is up until February 11th, 2025

Even after all the containers boot up, if there's some delay in getting events from relays, the frontend may say there's an error loading stats. If you wait until relay events come in, it should auto update.


