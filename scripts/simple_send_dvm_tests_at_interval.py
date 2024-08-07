"""
This script sends a DVM test every minute, and measures how long it takes before we see it in our db
"""
import asyncio
from nostr_sdk import (
    Keys,
    Client,
    EventBuilder,
    NostrSigner,
)

RELAYS = list(
    "wss://nostr-pub.wellorder.net,wss://relay.damus.io,wss://nos.lol,wss://relay.primal.net,wss://offchain.pub,wss://nostr.mom,wss://relay.nostr.bg,wss://nostr.oxtr.dev,wss://relay.nostr.bg,wss://nostr-relay.nokotaro.com,wss://relay.nostr.wirednet.jp".split(
        ","
    )
)


async def send_5000_event():
    # print("\tStarting to create the BROADCASTING client...")
    broadcasting_keys = Keys.generate()
    broadcasting_pk = broadcasting_keys.public_key()
    # print(
    #    f"\tNostr Test BROADCASTING Client public key: {broadcasting_pk.to_bech32()}, Hex: {broadcasting_pk.to_hex()} "
    # )
    broadcasting_signer = NostrSigner.keys(broadcasting_keys)
    broadcasting_client = Client(broadcasting_signer)
    # print("\tConnecting to relays for broadcasting client...")
    for relay in RELAYS:
        await broadcasting_client.add_relay(relay)
    await broadcasting_client.connect()

    # print(f"\tAbout to send event via the broadcasting client...")
    event_i = EventBuilder.text_note(
        f"\tWrite a poem about a data vending machine", []
    ).to_event(broadcasting_keys)

    # print(f"event as json: {event_i.as_json()}")

    # print(f"\tSending a {event_i.kind().as_u16()} test note with id: {event_i.id()}")
    output = await broadcasting_client.send_event(event_i)

    print(f"Sent event id: {event_i.id().to_hex()}, output is: {output}")

    # print(f"\tOutput: {output}")

    return str(event_i.id().to_hex())


async def start_broadcast():
    while True:
        recent_event_id = await send_5000_event()
        await asyncio.sleep(30)


if __name__ == "__main__":
    # asyncio.run(test())
    asyncio.run(start_broadcast())
