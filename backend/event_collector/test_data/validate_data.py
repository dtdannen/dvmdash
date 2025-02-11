import asyncio
import json
import time
from pathlib import Path
from typing import AsyncIterator, Dict, List
import argparse
from loguru import logger
import sys


class TestDataValidator:
    def __init__(
        self,
        filepath: str,
        batch_size: int = 10000,
        delay_between_batches: float = 0.0,
        max_batches: int = None,
    ):
        self.filepath = Path(filepath)
        self.batch_size = batch_size
        self.delay_between_batches = delay_between_batches
        self.max_batches = max_batches
        self.events_processed = 0
        self.events_invalid = 0
        self.batches_processed = 0
        self.last_header_time = 0
        self.header_interval = 20
        self.invalid_events = []

    async def validate_events(self) -> None:
        """Process and validate events from file in batches."""
        try:
            async for batch in self._read_batches():
                batch_invalid = 0
                batch_processed = 0

                for event in batch:
                    if self._is_valid_event(event):
                        batch_processed += 1
                    else:
                        batch_invalid += 1

                self.events_processed += batch_processed
                self.events_invalid += batch_invalid
                self.batches_processed += 1

                await self._print_stats()

                if self.delay_between_batches > 0:
                    await asyncio.sleep(self.delay_between_batches)

                if self.max_batches and self.batches_processed >= self.max_batches:
                    logger.info(f"\nReached maximum batch limit of {self.max_batches}")
                    break

        except Exception as e:
            logger.error(f"Error processing test data: {e}")
            raise

    def _is_valid_event(self, event: Dict) -> bool:
        required_fields = ["id", "kind", "pubkey", "created_at", "content"]

        if not all(field in event for field in required_fields):
            missing = [field for field in required_fields if field not in event]
            logger.warning(f"Event missing required fields: {missing}")
            return False

        try:
            if not isinstance(event["id"], str) or len(event["id"]) != 64:
                logger.warning(f"Invalid id format: {event['id']}")
                return False

            if not isinstance(event["kind"], int):
                logger.warning(f"Invalid kind format: {event['kind']}")
                return False

            if not isinstance(event["pubkey"], str) or len(event["pubkey"]) != 64:
                logger.warning(f"Invalid pubkey format: {event['pubkey']}")
                return False

            if not isinstance(event["created_at"], int):
                logger.warning(f"Invalid created_at format: {event['created_at']}")
                return False

            return True

        except Exception as e:
            logger.warning(f"Error validating event: {e}")
            return False

    async def _read_batches(self) -> AsyncIterator[List[Dict]]:
        """Read MongoDB export JSON file in batches."""
        try:
            logger.info(
                "Loading JSON file... (this might take a while for large files)"
            )
            with open(self.filepath, "r") as f:
                data = json.load(f)

            if not isinstance(data, list):
                raise ValueError("Expected JSON array at root level")

            logger.info(f"Loaded {len(data):,} events from file")

            # Process in batches
            for i in range(0, len(data), self.batch_size):
                if self.max_batches and self.batches_processed >= self.max_batches:
                    break

                batch = data[i : i + self.batch_size]
                yield batch

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON file: {e}")
            raise
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            raise

    async def _print_stats(self) -> None:
        current_time = time.time()

        if (
            self.events_processed % self.header_interval == 0
            or current_time - self.last_header_time > 60
        ):
            header = f"{'Time':^12}|{'Processed':^15}|{'Invalid':^15}|{'Batches':^10}"
            logger.info(header)
            logger.info("=" * len(header))
            self.last_header_time = current_time

        current_time_str = time.strftime("%H:%M:%S")
        logger.info(
            f"{current_time_str:^12}|{self.events_processed:^15d}|"
            f"{self.events_invalid:^15d}|{self.batches_processed:^10d}"
        )

    def print_summary(self):
        logger.info("\n=== Validation Summary ===")
        logger.info(f"Total events processed: {self.events_processed:,}")
        logger.info(f"Total invalid events: {self.events_invalid:,}")
        logger.info(f"Total batches processed: {self.batches_processed:,}")


async def main():
    parser = argparse.ArgumentParser(description="Validate MongoDB export JSON file")
    parser.add_argument("filepath", help="Path to the MongoDB export JSON file")
    parser.add_argument(
        "--batch-size", type=int, default=10000, help="Batch size for processing"
    )
    parser.add_argument(
        "--delay", type=float, default=0.0, help="Delay between batches in seconds"
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        help="Maximum number of batches to process (optional)",
    )
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stdout, colorize=True, level="INFO")

    validator = TestDataValidator(
        filepath=args.filepath,
        batch_size=args.batch_size,
        delay_between_batches=args.delay,
        max_batches=args.max_batches,
    )

    try:
        await validator.validate_events()
        validator.print_summary()
    except FileNotFoundError:
        logger.error(f"File not found: {args.filepath}")
    except Exception as e:
        logger.error(f"Error during validation: {e}")


if __name__ == "__main__":
    asyncio.run(main())
