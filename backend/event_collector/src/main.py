import asyncio
import sys
import nostr_sdk
import json
import os
from pathlib import Path
import loguru
from nostr_sdk import (
    Keys,
    Client,
    Filter,
    HandleNotification,
    Timestamp,
    LogLevel,
    Kind,
    Event,
    EventBuilder,
    Metadata,
)
import traceback
import argparse
import time
import yaml
import redis
from redis import Redis
from typing import Optional, List, Dict

from collector_manager import CollectorManager, RelayManager
from historical_processor import process_historical_data

# print all the env variables to the console, to see what we start with:
# print("Environment variables:")
# for key, value in os.environ.items():
#     print(f"{key}={value}")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
NOSTR_LOG_LEVEL = os.getenv("NOSTR_LOG_LEVEL", "INFO").upper()

# Simple logging setup that works well with Docker
logger = loguru.logger
logger.remove()  # Remove default handler
logger.add(sys.stdout, colorize=True, level=LOG_LEVEL)
nostr_sdk.init_logger(getattr(LogLevel, NOSTR_LOG_LEVEL))

# Default relay if no Redis configuration exists
DEFAULT_RELAYS = os.getenv("RELAYS", "wss://relay.dvmdash.live").split(",")

# Flag to track if profile note has been sent during this boot session
PROFILE_NOTE_SENT = False

def load_dvm_config():
    """Load DVM configuration from YAML file. Raises exceptions if file is not found or invalid."""
    config_path = Path("/app/backend/shared/dvm/config/dvm_kinds.yaml")

    if not config_path.exists():
        raise FileNotFoundError(f"Required config file not found at: {config_path}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    if not config:
        raise ValueError(f"Config file is empty: {config_path}")

    # Validate required fields
    required_fields = ["known_kinds", "ranges"]
    missing_fields = [field for field in required_fields if field not in config]
    if missing_fields:
        raise ValueError(f"Missing required fields in config: {', '.join(missing_fields)}")

    # Validate ranges structure
    required_range_fields = ["request", "result"]
    for range_field in required_range_fields:
        if range_field not in config["ranges"]:
            raise ValueError(f"Missing required range field: {range_field}")
        if (
            "start" not in config["ranges"][range_field]
            or "end" not in config["ranges"][range_field]
        ):
            raise ValueError(f"Range {range_field} missing start or end value")

    return config

def get_relevant_kinds() -> List[Kind]:
    """Get relevant kinds from config file. Will raise exceptions if config is invalid."""
    try:
        config = load_dvm_config()

        # Get explicitly known kinds
        known_kinds = [k["kind"] for k in config["known_kinds"]]

        # Generate ranges
        request_range = range(
            config["ranges"]["request"]["start"], config["ranges"]["request"]["end"]
        )
        result_range = range(
            config["ranges"]["result"]["start"], config["ranges"]["result"]["end"]
        )

        # Get excluded kinds
        excluded_kinds = {k["kind"] for k in config.get("excluded_kinds", [])}

        # Combine all kinds
        all_kinds = set(known_kinds + list(request_range) + list(result_range))

        # Remove excluded kinds
        valid_kinds = all_kinds - excluded_kinds

        logger.info(f"Loaded {len(valid_kinds)} valid kinds, and excluding kinds: {excluded_kinds}")

        return [Kind(k) for k in valid_kinds]
    except Exception as e:
        logger.error(f"Failed to get relevant kinds: {str(e)}")
        raise

# This will now raise an error if the config file can't be found or is invalid
RELEVANT_KINDS = get_relevant_kinds()

class EventDeduplicator:
    def __init__(
        self,
        redis_client: redis.Redis,
        max_events: int = 1_000_000,
        cleanup_threshold: float = 0.98,
    ):
        self.redis = redis_client
        self.set_key = "dvmdash_processed_events"
        self.zset_key = "dvmdash_event_timestamps"
        self.max_events = max_events
        self.cleanup_threshold = cleanup_threshold

    def check_duplicate(self, event_id: str) -> bool:
        """
        Check if event is duplicate and add to tracking if not.
        Returns True if duplicate, False if new.
        """
        try:
            timestamp = time.time()

            with self.redis.pipeline() as pipe:
                pipe.sadd(self.set_key, event_id)
                pipe.zadd(self.zset_key, {event_id: timestamp})
                results = pipe.execute()

                is_new = results[0]

                # Cleanup if needed
                if is_new and len(self.redis.zrange(self.zset_key, 0, -1)) >= self.max_events:
                    # Remove oldest events to get back to 95% capacity
                    target_size = int(self.max_events * 0.95)
                    to_remove = len(self.redis.zrange(self.zset_key, 0, -1)) - target_size
                    if to_remove > 0:
                        oldest_events = self.redis.zrange(self.zset_key, 0, to_remove - 1)
                        self.redis.zremrangebyrank(self.zset_key, 0, to_remove - 1)
                        self.redis.srem(self.set_key, *oldest_events)

                return not is_new

        except Exception as e:
            logger.error(f"Error checking duplicate: {e}")
            return False

class NotificationHandler(HandleNotification):
    def __init__(self, collector_manager: CollectorManager, relay_manager: RelayManager):
        self.events_processed = 0
        self.events_duplicate = 0
        self.last_header_time = 0
        self.header_interval = 20

        # Initialize Redis connection and managers
        self.redis = redis.from_url(REDIS_URL)
        self.deduplicator = EventDeduplicator(self.redis)
        self.collector_manager = collector_manager
        self.relay_manager = relay_manager

    async def handle(self, relay_url: str, subscription_id: str, event: Event):
        if event.kind() in RELEVANT_KINDS:
            try:
                event_json = json.loads(event.as_json())
                event_id = event_json["id"]

                # Check for duplicate before processing
                is_duplicate = self.deduplicator.check_duplicate(event_id)

                if not is_duplicate:
                    # Update metrics and add to processing queue
                    self.relay_manager.update_relay_metrics(relay_url, event_id)
                    self.redis.rpush("dvmdash_events", json.dumps(event_json))
                    self.events_processed += 1
                else:
                    self.events_duplicate += 1

                #await self.print_stats()

            except Exception as e:
                logger.error(f"Error processing event: {e}")
                logger.error(traceback.format_exc())

    async def print_stats(self):
        current_time = time.time()

        if (
            self.events_processed % self.header_interval == 0
            or current_time - self.last_header_time > 60
        ):
            header = f"{'Time':^12}|{'Processed':^15}|{'Duplicates':^15}"
            logger.info(header)
            logger.info("=" * len(header))
            self.last_header_time = current_time

        current_time_str = time.strftime("%H:%M:%S")
        logger.info(
            f"{current_time_str:^12}|{self.events_processed:^15d}|{self.events_duplicate:^15d}"
        )

    async def handle_msg(self, relay_url: str, message: str):
        logger.debug(f"Received message from {relay_url}: {message}")

async def create_profile_note(client: Client, collector_id: str, has_nsec_key: bool):
    """Create and broadcast a kind 0 profile note"""
    global PROFILE_NOTE_SENT
    
    # Check if we've already sent a profile note for this boot session
    if PROFILE_NOTE_SENT:
        logger.info("Profile note already sent for this boot session, skipping")
        return
    
    # Only send profile note if we have an nsec key
    if not has_nsec_key:
        logger.info("No nsec key assigned, skipping profile note creation")
        return
    
    try:
        logger.info("Creating and broadcasting kind 0 profile note")
        
        # Create metadata
        metadata = Metadata()
        metadata.name = f"DVMDash Event Listener {collector_id}"
        metadata.display_name = f"DVMDash Event Listener {collector_id}"
        metadata.about = "I'm an event listener that collects events from relays for https://stats.dvmdash.live. I do not send any events except a kind 0 profile event occasionally. Please consider whitelisting me if you'd like DVM events on your relay to show up on DVMDash"
        metadata.set_nip05(f"dvmdash-listener-{collector_id}@dvmdash.live")
        
        # Create and send event
        builder = EventBuilder.metadata(metadata)
        event = await client.sign_event_builder(builder)
        logger.info(f"About to send profile event:\n\n{event}\n\n")
        await client.send_event(event)
        
        logger.info(f"Successfully sent kind 0 profile note for collector {collector_id}")
        
        # Mark that we've sent a profile note for this boot session
        PROFILE_NOTE_SENT = True
        
    except Exception as e:
        logger.error(f"Error creating profile note: {e}")
        logger.error(traceback.format_exc())

async def nostr_client(collector_manager: CollectorManager, relay_manager: RelayManager, days_lookback=0):
    # Get assigned nsec key - wait until it's available
    nsec_key = None
    max_retries = 10
    retry_count = 0
    retry_delay = 2  # Start with 2 seconds
    
    while retry_count < max_retries:
        try:
            nsec_key_bytes = relay_manager.redis.get(f"dvmdash:collector:{relay_manager.collector_id}:nsec_key")
            if nsec_key_bytes:
                nsec_key = nsec_key_bytes.decode("utf-8")
                logger.info(f"[REDIS_DEBUG] Found assigned nsec key from Redis")
                break
            else:
                retry_count += 1
                logger.warning(f"[REDIS_DEBUG] No nsec key assigned yet, waiting (attempt {retry_count}/{max_retries})...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(30, retry_delay * 2)  # Exponential backoff, max 30 seconds
        except Exception as e:
            logger.error(f"[REDIS_DEBUG] Error getting assigned nsec key: {e}")
            retry_count += 1
            await asyncio.sleep(retry_delay)
            retry_delay = min(30, retry_delay * 2)
    
    # If we still don't have an nsec key after all retries, raise an exception
    if not nsec_key:
        error_msg = f"[REDIS_DEBUG] Failed to get nsec key after {max_retries} attempts"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Create signer with the assigned key
    try:
        signer = Keys.parse(nsec_key)
        logger.info(f"[REDIS_DEBUG] Using assigned nsec key for Nostr client")
    except Exception as e:
        error_msg = f"[REDIS_DEBUG] Error parsing assigned nsec key: {e}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        raise ValueError(error_msg)
    
    pk = signer.public_key()
    logger.info(f"Nostr Test Client public key: {pk.to_bech32()}, Hex: {pk.to_hex()}")

    client = Client(signer)

    # Get assigned relays from Redis
    logger.info(f"[REDIS_DEBUG] Requesting relay assignments from Redis...")
    try:
        relays = await relay_manager.get_assigned_relays()
        logger.info(f"[REDIS_DEBUG] Successfully received {len(relays)} relay assignments: {relays}")
    except Exception as e:
        logger.error(f"[REDIS_DEBUG] Error getting relay assignments: {e}")
        logger.error(traceback.format_exc())
        raise
    
    # Validate that we have relays to connect to
    if not relays:
        # This should not happen since get_assigned_relays should throw an exception if no relays are assigned
        # But just in case, let's handle it explicitly
        error_msg = f"[REDIS_DEBUG] No relays assigned to collector {relay_manager.collector_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Add all assigned relays
    for relay in relays:
        logger.info(f"[REDIS_DEBUG] Adding relay to client: {relay}")
        try:
            await client.add_relay(relay)
            logger.info(f"[REDIS_DEBUG] Successfully added relay: {relay}")
        except Exception as e:
            logger.error(f"[REDIS_DEBUG] Error adding relay {relay}: {e}")
    
    # Connect to all relays
    logger.info(f"[REDIS_DEBUG] Connecting to all relays...")
    try:
        await client.connect()
        logger.info(f"[REDIS_DEBUG] Successfully connected to relays")
    except Exception as e:
        logger.error(f"[REDIS_DEBUG] Error connecting to relays: {e}")
        logger.error(traceback.format_exc())
        raise

    days_timestamp = Timestamp.from_secs(
        Timestamp.now().as_secs() - (60 * 60 * 24 * days_lookback)
    )

    dvm_filter = Filter().kinds(RELEVANT_KINDS).since(days_timestamp)
    await client.subscribe([dvm_filter])

    notification_handler = NotificationHandler(collector_manager, relay_manager)
    handle_notifications_task = asyncio.create_task(
        client.handle_notifications(notification_handler)
    )

    return client, notification_handler, handle_notifications_task

async def listen_to_relays(args, collector_manager: CollectorManager, relay_manager: RelayManager):
    """Listen to relays for new events"""
    logger.info("[REDIS_DEBUG] Starting relay listener...")
    reconnect_interval = 240  # Reconnect every 4 minutes
    next_reconnect = time.time() + reconnect_interval

    # Register collector (which will trigger relay distribution)
    logger.info("[REDIS_DEBUG] Registering collector with Redis...")
    try:
        await collector_manager.register()
        logger.info("[REDIS_DEBUG] Collector registration successful")
    except Exception as e:
        logger.error(f"[REDIS_DEBUG] Error registering collector: {e}")
        logger.error(traceback.format_exc())
        raise
    
    # Wait a moment for relay distribution to take effect
    logger.info("[REDIS_DEBUG] Waiting for relay distribution to take effect...")
    await asyncio.sleep(2)
    logger.info("[REDIS_DEBUG] Continuing after waiting for relay distribution")

    while True:
        client = None
        handle_notifications_task = None
        try:
            logger.info(f"Connecting to relays (next reconnect at {time.strftime('%H:%M:%S', time.localtime(next_reconnect))})")
            
            # Try to connect with multiple retries
            max_retries = 5
            retry_count = 0
            retry_delay = 2  # Start with 2 seconds
            
            while retry_count < max_retries:
                try:
                    # Check if we need to request relay distribution
                    if retry_count > 0:
                        logger.info(f"Retry {retry_count}/{max_retries}: Requesting relay distribution...")
                        # Request relay distribution from coordinator
                        relay_manager.redis.set('dvmdash:settings:distribution_requested', '1', ex=300)  # Expire after 5 minutes
                        relay_manager.redis.set('dvmdash:settings:last_change', int(time.time()))
                        
                        # Wait for distribution to take effect
                        await asyncio.sleep(retry_delay)
                    
                    # Try to get client
                    client, notification_handler, handle_notifications_task = await nostr_client(
                        collector_manager, relay_manager, args.days_lookback
                    )
                    
                    # If we get here, we successfully connected
                    logger.info("Successfully connected to relays")
                    
                    # Send profile note after successful connection
                    # If we got here, we have an nsec key
                    await create_profile_note(client, relay_manager.collector_id, True)
                    
                    break
                    
                except ValueError as e:
                    # This could be due to no relays being assigned
                    retry_count += 1
                    if retry_count >= max_retries:
                        logger.error(f"Failed to connect after {max_retries} retries: {e}")
                        raise  # Re-raise to be caught by outer exception handler
                    
                    logger.error(f"Error getting assigned relays (retry {retry_count}/{max_retries}): {e}")
                    # Increase delay exponentially
                    retry_delay = min(30, retry_delay * 2)  # Cap at 30 seconds
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)

            # Check reconnect time while allowing notifications to process
            try:
                remaining_time = max(0.1, next_reconnect - time.time())
                await asyncio.wait_for(
                    handle_notifications_task,
                    timeout=remaining_time
                )
                logger.info("Notification handler completed naturally, will reconnect...")
            except asyncio.TimeoutError:
                logger.info("Reconnect interval reached, forcing reconnect...")
            except Exception as e:
                logger.error(f"Error in notification handler: {e}")
                logger.error(traceback.format_exc())
            
            # Clean up the current notification handler task
            if handle_notifications_task and not handle_notifications_task.done():
                handle_notifications_task.cancel()
                try:
                    await handle_notifications_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error cancelling notification handler: {e}")

            # Disconnect client and update next reconnect time
            if client:
                try:
                    await client.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting client: {e}")
            
            next_reconnect = time.time() + reconnect_interval
            logger.info(f"Disconnected. Next reconnect at {time.strftime('%H:%M:%S', time.localtime(next_reconnect))}")

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
            break
        except Exception as e:
            logger.error(f"Unhandled exception in main: {e}")
            logger.error(traceback.format_exc())
            await asyncio.sleep(10)
            next_reconnect = time.time() + reconnect_interval
        finally:
            if handle_notifications_task and not handle_notifications_task.done():
                handle_notifications_task.cancel()
                try:
                    await handle_notifications_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error in final task cleanup: {e}")

            if client:
                try:
                    await client.disconnect()
                except Exception as e:
                    logger.error(f"Error in final client cleanup: {e}")

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime",
        type=int,
        help="Number of minutes to run before exiting",
        default=-1,
    )
    parser.add_argument(
        "--days_lookback",
        type=int,
        help="Number of days in the past to ask relays for events, default is 0",
        default=int(os.getenv("DAYS_LOOKBACK", "1")),
    )
    parser.add_argument(
        "--start-listening",
        action="store_true",
        help="Start listening to relays immediately",
        default=(os.getenv("START_LISTENING", "false").lower() == "true"),
    )
    # historical data arguments
    parser.add_argument(
        "--historical-data",
        action="store_true",
        help="Load events from historical data files instead of connecting to relays",
        default=(os.getenv("LOAD_HISTORICAL_DATA", "false").lower() == "true"),
    )
    parser.add_argument(
        "--historical-data-urls",
        type=str,
        default=os.getenv("HISTORICAL_DATA_URLS", ""),
        help="Optional comma-separated list of specific historical data URLs. If not provided, will automatically discover and sort all available monthly data files.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("HISTORICAL_DATA_BATCH_SIZE", "10000")),
        help="Number of events to process in each batch when loading HISTORICAL data",
    )
    parser.add_argument(
        "--batch-delay",
        type=float,
        default=float(os.getenv("HISTORICAL_DATA_BATCH_DELAY", "0.001")),
        help="Delay in seconds between processing batches of HISTORICAL data",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        help="Maximum number of batches to process (optional)",
    )
    parser.add_argument(
        "--historical-months",
        type=int,
        default=int(os.getenv("HISTORICAL_MONTHS", "0")),
        help="Number of most recent months to process from historical data. If 0 or not set, processes all available months.",
    )
    return parser.parse_args()

async def main(args):
    """Main entry point with support for historical->relay transition"""
    # Initialize Redis client
    redis_client = redis.from_url(REDIS_URL)
    
    try:
        if args.historical_data:
            logger.info("Historical data mode enabled - will process historical data then switch to relays")
            # Process historical data without collector registration
            historical_success = await process_historical_data(
                REDIS_URL, 
                args,
                relevant_kinds=[k.as_u16() for k in RELEVANT_KINDS]
            )
            
            if historical_success and args.start_listening:
                logger.info("Historical data processing complete - switching to relay mode")
                # Now initialize collector for relay mode
                collector_manager = CollectorManager(redis_client)
                relay_manager = RelayManager(redis_client, collector_manager.collector_id)
                await listen_to_relays(args, collector_manager, relay_manager)
            else:
                logger.info("Not starting relay listener as --start-listening is not enabled")
        else:
            if not args.start_listening:
                logger.info(
                    "Not listening to relays. Set START_LISTENING=true to begin or run "
                    "`START_LISTENING=true docker compose restart event_collector` after all containers are up."
                )
                while True:
                    await asyncio.sleep(3600)  # Sleep for an hour
            else:
                # Start in relay mode
                collector_manager = CollectorManager(redis_client)
                relay_manager = RelayManager(redis_client, collector_manager.collector_id)
                await listen_to_relays(args, collector_manager, relay_manager)
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        logger.error(traceback.format_exc())
        raise
    finally:
        # Ensure Redis client is closed
        redis_client.close()

if __name__ == "__main__":
    logger.info("[REDIS_DEBUG] Starting event collector...")
    args = parse_args()
    
    # Log Redis connection info
    logger.info(f"[REDIS_DEBUG] Using Redis URL: {REDIS_URL}")
    
    # Test Redis connection
    try:
        test_redis = redis.from_url(REDIS_URL)
        ping_result = test_redis.ping()
        logger.info(f"[REDIS_DEBUG] Redis connection test: {ping_result}")
        
        # Check if coordinator is running
        coordinator_heartbeat = test_redis.get('dvmdash:coordinator:heartbeat')
        logger.info(f"[REDIS_DEBUG] Coordinator heartbeat: {coordinator_heartbeat}")
        
        # Check active collectors
        active_collectors = test_redis.smembers('dvmdash:collectors:active')
        logger.info(f"[REDIS_DEBUG] Active collectors: {active_collectors}")
        
        # Check relay configuration
        relays_config = test_redis.get('dvmdash:settings:relays')
        if relays_config:
            relays_dict = json.loads(relays_config)
            logger.info(f"[REDIS_DEBUG] Found {len(relays_dict)} relays in configuration")
        else:
            logger.warning("[REDIS_DEBUG] No relay configuration found in Redis")
            
        test_redis.close()
    except Exception as e:
        logger.error(f"[REDIS_DEBUG] Redis connection test failed: {e}")
        logger.error(traceback.format_exc())

    async def run_program():
        try:
            if args.runtime > 0:
                await asyncio.wait_for(main(args), timeout=(args.runtime * 60))
            else:
                await main(args)
        except FileNotFoundError as e:
            logger.error(f"[REDIS_DEBUG] Configuration error: {e}")
            sys.exit(1)
        except ValueError as e:
            logger.error(f"[REDIS_DEBUG] Invalid configuration: {e}")
            sys.exit(1)
        except asyncio.TimeoutError:
            logger.info(f"Program ran for {args.runtime} minutes and is now exiting.")
        except redis.exceptions.ConnectionError as e:
            logger.error(f"[REDIS_DEBUG] Redis connection error: {e}")
            logger.error(traceback.format_exc())
            sys.exit(1)
        except Exception as e:
            logger.error(f"[REDIS_DEBUG] Fatal error: {e}")
            traceback.print_exc()
            sys.exit(1)

    try:
        asyncio.run(run_program())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    finally:
        logger.info("Program exiting...")
