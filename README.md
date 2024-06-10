# dvmdash

DVMDash aims to be a monitoring and debugging tool for DVM activity on Nostr. Data Vending Machines (nip-90) offload computationally expensive tasks from relays and clients in a decentralized, free-market manner. They are especially useful for AI tools, algorithmic processing of user’s feeds, and many other use cases.

The project is pre-alpha. Main branch is not guaranteed to be stable.

A version of the website is running here:

https://dvmdash.live/

## Install

- Use Python3.11
  - As of May 13th, 2024, Python 3.12 is unsupported
- If you are only using scripts/ (i.e. listengin for DVM events, you should only need requirements_backend.txt)

## How to run this locally

Run Mongita or a MongoDB locally

Run Neo4j

- See https://neo4j.com/docs/operations-manual/current/installation/
- Once you have the tar file, you can run it with `./neo4j start`
- Then check it's running in the web browser at `http://localhost:7474/`

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