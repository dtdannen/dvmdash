# Data Vending Machines

A Data Vending Machine (DVM) is a service provided on the Nostr network. DVMs were originally intended to perform computation for money, aka "money in, data out", although they are not limited to this (see the section below on humans as DVMs). DVMs operate on Nostr at the same level as human users; each DVM has an npub/nsec and publishes events like users, with the primary difference being that DVMs generally listen for request events (kind ranges 5000-5999) and respond with feedback events (kind 7000) and response events (kind 6000-6999), where response events should match the request event kind, except starting with a 6 instead of a 5 (so a 5050 request by a user should get a response of 6050 by a DVM).

While human users create profile events using kind 0 events (see [[NIP-01]]), DVMs publish profile data in the form of kind 31990 (see [[NIP-89]]), which includes information on the parameters that should be used for calling the DVM. For example, translation requests should include a target language field like 'en' for English.

A special feature of the DVM ecosystem is the separation of DVMs and users via kind numbers. Like Nostr is not peer-to-peer because users do not connect to users directly, instead they use relays as intermediaries, when a user uses a DVM they do not request the DVM specifically. Instead the user requests a kind number corresponding to the type of work they wish to have done, and whichever DVMs are available and interested will respond. This is unusual compared to other decentralized AI approaches (such as fetch.ai or singularitynet) that expect AI services to directly connect to one another and users. Thus, the DVM ecosystem is more dynamic and flexible because (1) a user doesn't need to know which DVM to use at the time they make their request, (2) DVMs can observe one another and attempt to out compete others such as offering lower prices, and (3) third parties can monitor DVM activity for failures or other issues, and start responding to the original request event to offer recovery services.

## Tradeoffs

- Users want privacy and may wish to encrypt requests directly for certain DVMs to operate on their data, so that only the user and the DVM see the request data and any response data. However, doing so reduces the ability for other DVMs to compete on price or to step in and offer services if the original DVM fails to respond.


## How DVMs Work

![DVM Process Flow Diagram](https://github.com/dtdannen/dvmdash/blob/main/docs%2FDVM_Process_Flow.png)

In the simplest case, interacting with a DVM is as follows:

1. A user makes a request (kind 5000-5999).
2. One or more DVMs respond with a response event (kind 6000-6999).

However, in most cases DVMs will expect to be paid for their work or require other conditions be met before responding with the result of the work, like as follows:

1. A user makes a request (kind 5000-5999).
2. One or more DVMs respond with a feedback event requesting payment or other conditions (kind 7000).
3. The user pays the invoice from the DVM feedback event (or zaps the DVM).
4. After receiving payment the DVMs perform the work and respond with a response event (kind 6000-6999).

## History of DVMs

@pablo published the first version of [[NIP-90]] on [July 3rd, 2023](https://github.com/nostr-protocol/nips/commit/67e950a2009e81df1b8c91b0a2ade0596e83f168)


## Humans as DVMs

Since DVMs operate on Nostr in the same capacity as human users, it is trivial for humans to perform work as if they were a DVM. All that would be needed is for a human to publish a [[NIP-89]] profile event and then the human user would simply need an interface to watch for request events that they would be interested in, respond asking for payment, and upon receiving payment, perform the work and respond with results in a corresponding response event. Currently no such app exists. 

## Opportunities to Improve the DVM Ecosystem

- Reputation management for DVMs
- Tools for Humans to Act as DVMs


## Projects and Companies Related to DVMs

- [data-vending-machines.org](https://www.data-vending-machines.org/) - A website providing some specs for DVMs and other useful information.
- [OpenAgents](https://docs.openagents.com/python-sdk) - The company OpenAgents runs individual agent nodes as DVMs.
- [vendata.io](vendata.io) - A web client that enables users to interact with a limited set of DVM kinds.
- [tasktiger.io](https://tasktiger.io/) - A company that operates DVMs for a variety of tasks.
- [DVMDash](https://github.com/dtdannen/dvmdash) - A monitoring and debugging tool for DVM activity on Nostr, currently in pre-alpha.

## DVM Implementations and Examples

- [nostr-data-vending-machine](https://github.com/pablof7z/nostr-data-vending-machine) - An example DVM built by @pablo written in typescript.
- [dvm-references](https://github.com/pablof7z/dvm-references/) - A reference implementation of a DVM (Data Vending Machine) backend]
- [DVM Clients and Services Tutorial](https://www.youtube.com/watch?v=dAuLnNxU0Yg) - Nostr Data Vending Machine Clients and Services Tutorial by Kody Low
- [nostr-dvm-ts](https://github.com/Kodylow/nostr-dvm-ts) - Typescript examples of Nostr Data Vending Machines
- [nostrdvm](https://github.com/believethehype/nostrdvm) - A Nostr NIP90 Data Vending Machine Framework in python