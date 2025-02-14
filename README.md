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


By default, it's set to pull dvm events from relays over the last 20 days (although many relays don't keep the events that long, so you may just see data from the last day or two). If you want to use historical data from last month and the current month, set `LOAD_HISTORICAL_DATA=true` in the `docker-compose.yml` file under the section `event_collector`. Once it's done pulling historical data, it will start listening to relays for more recent events. Keep in mind this requires a few GB of data. The historical data available is up until February 11th, 2025

Event after all the containers boot up, if there's some delay in getting events from relays, the frontend may say there's an error loading stats. If you wait until relay events come in, it should auto update.


### Old Instructions Below

## Local Development

After you make changes, and want to run the docker, make sure to rebuild the containers like:

```commandline
docker compose up --build -d
```

First, check that the all the services are running:

```commandline
docker compose ps
```

After the containers are up and running, run:

```commandline
docker compose --profile test up tests
```




## Run Locally

These instructions aren't complete but hopefully are helpful for those with some experience with Django, mongo db, and neo4j. Feel free to open an issue if you have any problems running this locally. We will write better instructions after we refactor the backend architecture. 

1. Clone the repo and create a virtual env (tested with Python3.12 but other versions may work)

```commandline
git clone https://github.com/dtdannen/dvmdash.git
cd dvmdash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e . # this is so the general/ folder is available to the django app
```

2. Get a neo4j and mongo db running

- Neo4j is used to store the graph of DVM events 
  - You can use hosted instances or local instances.
  - Neo4j offers a free hosted solution for testing, which has enough capacity to test out the system. See https://neo4j.com/product/auradb/?ref=neo4j-home-hero
  - If you are running neo4j locally, 
    - See https://neo4j.com/docs/operations-manual/current/installation/
    - Once you have the tar file, you can run it with `./neo4j start`
       - Or ` ~/bin/neo4j-community-5.20.0/bin/neo4j start`
   - Then check it's running in the web browser at `http://localhost:7474/`


- Mongo DB should be straightforward 
  - Often, running mongodb locally looks like: 
    ```commandline
    ./mongod --dbpath ~/mongodb/data/db
    ```
    
3. Populate the .env file with the connection parameters for your databases

- You can copy the .env.example file to .env and fill in the connection parameters for your databases.

4. Run the background scripts to start collecting DVM related events from relays. If you don't do this step, the django web app will not have any data or metrics to show. Run each one of them in their own terminal window. If running these on a server, consider `screen` or run them as a cron job.
 
   - [run_asyncio_listen_for_DVM_events.sh](scripts%2Frun_asyncio_listen_for_DVM_events.sh)
   - [run_compute_stats.sh](scripts%2Frun_compute_stats.sh)

5. Run the Django web app

```commandline
# ensure virtualenv is activated (i.e. source venv/bin/activate)
# ensure you're at the project root
python dvmdash/manage.py runserver
```

It may take a few seconds to connect to both neo4j and mongo databases. Once it's running, you can view the web app at `http://localhost:8000/`


# Other Misc Notes

## How to update javascript via npm

- After you've added a new library to the package.json file and made any changes to webpack.config.js, you can run `npm run build` to update the javascript files in the static/ directory in the monitor/static/ directory.
- Then run `python dvmdash/manage.py collectstatic` to update the static files in the main staticfiles/ directory, which is where static files are served when running locally.


## How to run this locally

1. Run a MongoDB locally

    - for example, run mongo locally:
      - `./mongod --dbpath ~/mongodb/data/db`

2. Run Neo4j

   - See https://neo4j.com/docs/operations-manual/current/installation/
   - Once you have the tar file, you can run it with `./neo4j start`
     - Or ` ~/bin/neo4j-community-5.20.0/bin/neo4j start`
   - Then check it's running in the web browser at `http://localhost:7474/`

3. (Optional) Run a local DVM
4. (Optional) Run a local relay, such as [bucket](https://github.com/coracle-social/bucket)
   - this is helpful to test local dvms with the playground page, testing sending and receiving DVM events.


### APOC Extension

- Download the APOC library JAR file that matches your Neo4j version from the APOC releases page on GitHub: https://github.com/neo4j/apoc/releases
- Copy the APOC JAR file to the plugins directory of your Neo4j installation. For example, if you're using Neo4j 4.x, the path would be neo4j-home/plugins/.
- Open the neo4j.conf configuration file located in the conf directory of your Neo4j installation.
- Uncomment or add the following line to the neo4j.conf file to enable the APOC library: `dbms.security.procedures.unrestricted=apoc.*`

## Neo4j Graph Structure

![DVM_Process_Flow.png](docs%2FDVM_Process_Flow.png)

The graph structure of events is stored in a Neo4j database.

#### Nodes:

- Entity:
  - These have an npub, and contain all users and DVMs
- Event:
  - These are Nostr events signed by Entities
- Invoice:
  - Data that contains information for a payment. Events refer to these
- Payment Receipt:
  - Data showing a receipt of purchase, such as a zap receipt.

#### Relationships:

Note that these are the primitive relationships. There will be other, inferred relationships later based on the primitive ones.

- MAKES_EVENT:  _# Used any time an entity makes an event_
  - Entity -> Event
- FEEDBACK_FOR:  _# Used to connect a DVM feedback event to the original request_
  - Event -> Event
- RESULT_FOR:  _# Used to connect a DVM result event to the original request_
  - Event -> Event
- HAS_INVOICE:  _# Used to connect a feedback event to an invoice_
  - Event -> Invoice
- HAS_RECEIPT:  _# Used to connect an invoice to a payment receipt_
  - Invoice -> Payment Receipt
- PAYMENT_FROM:  _# Used to connect a payment receipt to the entity that paid_
  - Payment Receipt -> Entity
- PAYMENT_TO:  _# Used to connect a payment receipt to the entity that received the payment_
  - Payment Receipt -> Entity


## List of Relays to Watch for DVM Events

These are the relays where we watch for DVM events.

- wss://nostr-pub.wellorder.net
- wss://relay.damus.io
- wss://nos.lol
- wss://relay.primal.net
- wss://offchain.pub
- wss://nostr.mom
- wss://relay.nostr.bg
- wss://nostr.oxtr.dev
- wss://relay.nostr.bg
- wss://nostr-relay.nokotaro.com
- wss://relay.nostr.wirednet.jp