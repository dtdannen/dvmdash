"""
A script to pull some wiki pages from relays to see what they look like.
"""

import asyncio
from datetime import timedelta
from nostr_sdk import *


async def main():
    # Init logger
    init_logger(LogLevel.INFO)

    # Initialize client without signer
    client = Client()

    # Add relays and connect
    await client.add_relay("wss://relay.damus.io")
    await client.add_relay("wss://nos.lol")
    await client.connect()

    # Get events from relays
    print("Getting events from relays...")
    # get wiki events published in the last 7 days
    f = (
        Filter()
        .kinds([Kind(30818)])
        .since(Timestamp.from_secs(Timestamp.now().as_secs() - (60 * 60 * 24 * 7)))
    )
    events = await client.fetch_events([f], timedelta(seconds=10))
    for event in events.to_vec():
        print(event.as_json())


if __name__ == "__main__":
    asyncio.run(main())
