import asyncio
from asyncio import Queue
import ast
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
)
from neo4j import AsyncGraphDatabase
import motor.motor_asyncio
import pymongo  # used only to create new collections if they don't exist
from pymongo.errors import BulkWriteError
from general.dvm import EventKind
from general.helpers import hex_to_npub, sanitize_json, format_query_with_params
import traceback
from bson.json_util import dumps

RELAYS = list(
    "wss://nostr-pub.wellorder.net,wss://relay.damus.io,wss://nos.lol,wss://relay.primal.net,wss://offchain.pub,wss://nostr.mom,wss://relay.nostr.bg,wss://nostr.oxtr.dev,wss://relay.nostr.bg,wss://nostr-relay.nokotaro.com,wss://relay.nostr.wirednet.jp".split(
        ","
    )
)

RELEVANT_KINDS = [Kind(k) for k in range(5000, 7001)]


class NotificationHandler(HandleNotification):
    def __init__(self, max_batch_size=100, max_wait_time=3):
        self.event_ids_seen = set()

    async def handle(self, relay_url, subscription_id, event: Event):
        # self.count_new_seen_event()
        if event.kind() in RELEVANT_KINDS:
            self.event_ids_seen.add(str(event.id().to_hex()))
            print(f"Adding event id: {event.id().to_hex()}")

    async def handle_msg(self, relay_url: str, message: str):
        # Implement this method
        pass


async def nostr_client():
    keys = Keys.generate()
    pk = keys.public_key()
    print(f"Nostr Test Client public key: {pk.to_bech32()}, Hex: {pk.to_hex()} ")
    signer = NostrSigner.keys(keys)
    client = Client(signer)
    for relay in RELAYS:
        await client.add_relay(relay)
    await client.connect()

    now_timestamp = Timestamp.now()
    # prev_24hr_timestamp = Timestamp.from_secs(Timestamp.now().as_secs() - 60 * 60 * 24)
    # prev_30days_timestamp = Timestamp.from_secs(
    #    Timestamp.now().as_secs() - 60 * 60 * 24 * 30
    # )

    dvm_filter = Filter().kinds(RELEVANT_KINDS).since(now_timestamp)
    await client.subscribe([dvm_filter])

    # Your existing code without the while True loop
    notification_handler = NotificationHandler()
    await client.handle_notifications(notification_handler)
    return client, notification_handler  # Return the client for potential cleanup


if __name__ == "__main__":
    asyncio.run(nostr_client())
