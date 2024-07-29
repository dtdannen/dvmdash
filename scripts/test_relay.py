"""
Tests a relay for many different kinds of events to see if it's working or not working

What this script does:
1. Create and broadcast an event for each kind, and then listen to see if that event is seen be a subscription to
the relay
"""


import asyncio
import copy
from asyncio import Queue
from collections import deque
import random
import sys
from datetime import datetime, timedelta
import nostr_sdk
import json
import os
import time
from pathlib import Path
from threading import Thread, Lock
import ctypes
import loguru
import dotenv
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
    RelayLimits,
)
from neo4j import AsyncGraphDatabase
import motor.motor_asyncio
import pymongo  # used only to create new collections if they don't exist
from pymongo.errors import BulkWriteError
from general.dvm import EventKind

RELEVANT_KINDS = [Kind(x) for x in [1]]

# ALL Relays: wss://nostr-pub.wellorder.net,wss://relay.damus.io,wss://nos.lol,wss://relay.primal.net,wss://offchain.pub,wss://nostr.mom,wss://relay.nostr.bg,wss://nostr.oxtr.dev,wss://relay.nostr.bg,wss://nostr-relay.nokotaro.com,wss://relay.nostr.wirednet.jp
RELAYS = list(
    "wss://nostr-pub.wellorder.net,wss://relay.damus.io,wss://nos.lol,wss://relay.primal.net,wss://offchain.pub,wss://nostr.mom,wss://relay.nostr.bg,wss://nostr.oxtr.dev,wss://relay.nostr.bg,wss://nostr-relay.nokotaro.com,wss://relay.nostr.wirednet.jp".split(
        ","
    )
)
CURRENT_RELAYS = []

events_broadcasted = []

events_seen = []

listening_client_creation_timestamp = None
events_seen_after_listening_client_created = []

number_of_tests = 5

messages_received_from_relay = []
events_received_from_relay = []
broadcast_events_received = []


class NotificationHandler(HandleNotification):
    def __init__(self):
        pass

    async def handle(self, relay_url, subscription_id, event: Event):
        events_seen.append(event)
        event_id = event.id()
        if event.created_at().as_secs() > listening_client_creation_timestamp.as_secs():
            difference = (
                event.created_at().as_secs()
                - listening_client_creation_timestamp.as_secs()
            )
            print(
                f"\tEvent {event_id} was created {difference}s after we started listening"
            )
            events_seen_after_listening_client_created.append(event)
        if event_id in events_broadcasted:
            print(f"\t!!Found an event that we broad casted!: {event_id}")
            broadcast_events_received.append(event_id)
        else:
            events_received_from_relay.append(event_id)

    async def handle_msg(self, relay_url: str, message: str):
        # Implement this method
        messages_received_from_relay.append(message)


async def nostr_client():
    # disable all limits
    limits = RelayLimits.disable()
    opts = Options().relay_limits(limits)

    print("\tStarting to create the BROADCASTING client...")
    broadcasting_keys = Keys.generate()
    broadcasting_pk = broadcasting_keys.public_key()
    print(
        f"\tNostr Test BROADCASTING Client public key: {broadcasting_pk.to_bech32()}, Hex: {broadcasting_pk.to_hex()} "
    )
    broadcasting_signer = NostrSigner.keys(broadcasting_keys)
    broadcasting_client = Client.with_opts(broadcasting_signer, opts)
    print("\tConnecting to relays for broadcasting client...")
    for relay in CURRENT_RELAYS:
        await broadcasting_client.add_relay(relay)
    await broadcasting_client.connect()

    print("\tStarting to create the listening client...")
    listening_keys = Keys.generate()
    listening_pk = listening_keys.public_key()
    print(
        f"\tNostr Test Listening Client public key: {listening_pk.to_bech32()}, Hex: {listening_pk.to_hex()}"
    )
    listening_signer = NostrSigner.keys(listening_keys)
    listening_client = Client.with_opts(listening_signer, opts)
    print("\tConnecting to relays for listening client...")
    for relay in RELAYS:
        await listening_client.add_relay(relay)
    await listening_client.connect()

    print(f"\tSubscribing to event kinds: {RELEVANT_KINDS}")
    global listening_client_creation_timestamp
    listening_client_creation_timestamp = Timestamp.now()
    dvm_filter = (
        Filter().kinds(RELEVANT_KINDS).since(listening_client_creation_timestamp)
    )
    await listening_client.subscribe([dvm_filter])

    print(f"\tAttaching the notification handler to the listening client...")
    notification_handler = NotificationHandler()
    await listening_client.handle_notifications(notification_handler)

    print(
        f"\tAbout to start sending random events of the particular kind via the broadcasting client..."
    )

    for i in range(number_of_tests):
        test_id = random.randint(1, 100000)

        event_i = EventBuilder.text_note(
            f"\tTest {test_id}: does this relay treat DVM kinds correctly....", []
        ).to_event(broadcasting_keys)
        print(f"\tSending a test note {test_id} with id: {event_i.id()}")
        output = await broadcasting_client.send_event(event_i)
        print(f"\tOutput: {output}")
        # print(f"\tSuccessfully sent to:    {output.}")
        # print(f"\tFailed to send to: {output.failed}")

        rand_sleep_delay = random.randint(5, 15)
        print(f"\tWaiting {rand_sleep_delay} before sending next test message")
        await asyncio.sleep(rand_sleep_delay)

    print(f"\tDisconnecting broadcasting client...")
    await broadcasting_client.disconnect()
    await asyncio.sleep(3)

    print(
        f"\t****** SUMMARY ******\n\t{len(broadcast_events_received)}/{number_of_tests} sent and received | total events seen: {len(events_received_from_relay)} | relay messages received: {len(messages_received_from_relay)}"
    )

    print(f"\tDisconnecting listening client...")
    await listening_client.disconnect()
    return listening_client


if __name__ == "__main__":
    SHUFFLED_RELAYS = copy.copy(RELAYS)
    random.shuffle(SHUFFLED_RELAYS)
    for relay_url in SHUFFLED_RELAYS:
        messages_received_from_relay = []
        events_received_from_relay = []
        broadcast_events_received = []

        CURRENT_RELAYS = [relay_url]
        print(
            f"=======================================================\n    Now testing relay: {relay_url}\n"
            f"======================================================="
        )
        loop = asyncio.get_event_loop()
        listening_client_i = None
        try:
            listening_client_i = loop.run_until_complete(nostr_client())
        except KeyboardInterrupt:
            break
        except Exception as e:
            import traceback

            traceback.print_exc()
        finally:
            if listening_client_i:
                loop.run_until_complete(listening_client_i.disconnect())
