# dvmdash

DVMDash is a webapp to monitor and debug Data Vending Machine (DVM) activity on Nostr. Data Vending Machines (nip-90) offload computationally expensive tasks from relays and clients in a decentralized, free-market manner. They are especially useful for AI tools, algorithmic processing of user’s feeds, and many other use cases.


A version of the website is running here:

https://dvmdash.live/

## Overview

DVMDash consists of two main parts:
- Django + Bootstrap web app displaying metrics, events, playground, and more
- Python server scripts located in `nostr_workers\ ` listening for DVM events from relays, processing the data for a no sql and graph databases, and computing metrics 
  - The scripts run independently of the Django web app and populate two databases:
    - a mongo db containing raw DVM events and stats
    - a neo4j db containing a graph structure of the DVM events which is primarily used for the debug page
      - however some metrics, like estimated earnings, are also calculated from the neo4j db

## Setup

1. Populate the .env file with the necessary environment variables (see env_default for an example)
   - RELAYS: a comma-separated list of relay URLs to watch for DVM events
   - MONGO_URI: the URI for the mongo db
   - NEO4J_URI: the URI for the neo4j db
   - NEO4J_USER: the username for the neo4j db
   - NEO4J_PASSWORD: the password for the neo4j db
   - DEBUG: set to True to enable debug mode (do not use in production, this is used by the Django web app)
   - DEVELOPMENT_MODE: if True, uses a sql lite DB for Django (note that unlike other Django apps, we currently do not use the Django ORM for anything at the moment)
   
2. Setup the python environment for the background scripts
   - `python3.12 -m venv scripts_venv`
   - `source scripts_venv/bin/activate`
   - `pip install -r requirements_scripts.txt`

3. 





Better installation instructions are coming soon!

Besides the Django web app, the following scripts should be running with access to the same databases used by the webapp:
- [run_asyncio_listen_for_DVM_events.sh](scripts%2Frun_asyncio_listen_for_DVM_events.sh)
- [run_compute_stats.sh](scripts%2Frun_compute_stats.sh)

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