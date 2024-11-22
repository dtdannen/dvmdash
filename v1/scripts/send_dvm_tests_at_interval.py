"""
This script sends a DVM test every minute, and measures how long it takes before we see it in our db
"""
import asyncio
import os
import loguru
import nostr_sdk
from pathlib import Path
import dotenv
import sys
from nostr_sdk import (
    Keys,
    Client,
    Tag,
    EventBuilder,
    Filter,
    HandleNotification,
    Timestamp,
    nip04_decrypt,
    LogLevel,
    NostrSigner,
    Kind,
    SubscribeAutoCloseOptions,
    Options,
    Event,
)
import motor.motor_asyncio

RELAYS = list(
    "wss://nostr-pub.wellorder.net,wss://relay.damus.io,wss://nos.lol,wss://relay.primal.net,wss://offchain.pub,wss://nostr.mom,wss://relay.nostr.bg,wss://nostr.oxtr.dev,wss://relay.nostr.bg,wss://nostr-relay.nokotaro.com,wss://relay.nostr.wirednet.jp".split(
        ","
    )
)

events_broadcasted = []

events_seen = []

listening_client_creation_timestamp = None
events_seen_after_listening_client_created = []


def setup_environment():
    env_path = Path(".env")
    if env_path.is_file():
        print(f"Loading environment from {env_path.resolve()}")
        dotenv.load_dotenv(env_path, verbose=True, override=True)
    else:
        print(f".env file not found at {env_path} ")
        raise FileNotFoundError(f".env file not found at {env_path} ")


setup_environment()


def setup_database():
    print("os.getenv('USE_MONGITA', False): ", os.getenv("USE_MONGITA", False))

    # connect to async db
    async_mongo_client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGO_URI"))
    async_db = async_mongo_client["dvmdash"]

    try:
        result = async_db["events"].count_documents({})
        print(f"There are {result} documents in events collection")
    except Exception as e:
        print("Could not count documents in async_db")
        import traceback

        traceback.print_exc()

    print("Connected to cloud mongo async_db")

    return async_db


ASYNC_MONGO_DB = setup_database()


async def send_5000_event():
    print("\tStarting to create the BROADCASTING client...")
    broadcasting_keys = Keys.generate()
    broadcasting_pk = broadcasting_keys.public_key()
    print(
        f"\tNostr Test BROADCASTING Client public key: {broadcasting_pk.to_bech32()}, Hex: {broadcasting_pk.to_hex()} "
    )
    broadcasting_signer = NostrSigner.keys(broadcasting_keys)
    broadcasting_client = Client(broadcasting_signer)
    print("\tConnecting to relays for broadcasting client...")
    for relay in RELAYS:
        await broadcasting_client.add_relay(relay)
    await broadcasting_client.connect()

    print(f"\tAbout to send event via the broadcasting client...")
    event_i = EventBuilder.text_note(
        f"\tWrite a poem about a data vending machine", []
    ).to_event(broadcasting_keys)

    print(f"event.id().to_hex(): {event_i.id().to_hex()}")
    print(f"event as json: {event_i.as_json()}")

    print(f"\tSending a {event_i.kind().as_u16()} test note with id: {event_i.id()}")
    output = await broadcasting_client.send_event(event_i)

    print(f"\tOutput: {output}")

    return str(event_i.id().to_hex())


async def setup_database():
    print("os.getenv('USE_MONGITA', False): ", os.getenv("USE_MONGITA", False))

    # connect to async db
    async_mongo_client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGO_URI"))
    async_db = async_mongo_client["dvmdash"]

    try:
        result = await async_db["events"].count_documents({})
        print(f"There are {result} documents in events collection")
    except Exception as e:
        print("Could not count documents in async_db")
        import traceback

        traceback.print_exc()

    print("Connected to cloud mongo async_db")

    return async_db


async def check_if_any_event_has_this_id(db, event_id):
    """
    Checks our db to see if we get any events that match the given event ID
    """
    mongo_query = {"id": event_id}

    result = await db.events.find_one(mongo_query)

    return result  # This will return None if no document is found


async def check_if_any_event_has_e_tag(db, event_id):
    mongo_query = {"tags": ["e", event_id]}

    cursor = db.events.find(mongo_query)
    related_docs = await cursor.to_list(length=None)

    return len(related_docs)


async def test():
    db = await setup_database()

    while True:
        # now poll the db until we see some events
        known_event_id = (
            "95ca5f50eeed2db644c0861d569a6b5e3ba30f60920ac04610bc9f14a492d924"
        )

        has_main_event = await check_if_any_event_has_this_id(db, known_event_id)

        if has_main_event:
            print(f"Got main event: {has_main_event}")
        else:
            print("No main event found")

        has_refer_events = await check_if_any_event_has_e_tag(db, known_event_id)

        print(f"Got {has_refer_events} refer events")

        await asyncio.sleep(1.0)


async def start_broadcast():
    db = await setup_database()

    while True:
        recent_event_id = await send_5000_event()

        has_main_event = None
        has_referer_events = None
        print(f"Now looking for event: {recent_event_id}")
        for i in range(15):
            has_main_event = await check_if_any_event_has_this_id(db, recent_event_id)

            if has_main_event:
                print(f"({i}s) Got main event: {has_main_event}")
            else:
                print(f"({i}s) No main event found")

            has_refer_events = await check_if_any_event_has_e_tag(db, recent_event_id)

            print(f"({i}s) Got {has_refer_events} refer events")

            await asyncio.sleep(1.0)

        if has_main_event is None and has_referer_events is None:
            print(
                f"We never received any events from relays based on our sent event with id: {recent_event_id}"
            )

        print("Sending a new test event...")


if __name__ == "__main__":
    # asyncio.run(test())
    asyncio.run(start_broadcast())
