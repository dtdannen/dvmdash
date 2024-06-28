# dvmdash

DVMDash aims to be a monitoring and debugging tool for DVM activity on Nostr. Data Vending Machines (nip-90) offload computationally expensive tasks from relays and clients in a decentralized, free-market manner. They are especially useful for AI tools, algorithmic processing of user’s feeds, and many other use cases.

The project is pre-alpha. Main branch is not guaranteed to be stable.

A version of the website is running here:

https://dvmdash.live/

## Install

- Use Python3.11
  - As of May 13th, 2024, Python 3.12 is unsupported
- If you are only using scripts/ (i.e. listengin for DVM events, you should only need requirements_backend.txt)


## How to update javascript via npm

- After you've added a new library to the package.json file and made any changes to webpack.config.js, you can run `npm run build` to update the javascript files in the static/ directory in the monitor/static/ directory.
- Then run `python dvmdash/manage.py collectstatic` to update the static files in the main staticfiles/ directory, which is where static files are served when running locally.


## How to run this locally

1. Run Mongita or a MongoDB locally

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

## Graph Structure

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