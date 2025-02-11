import ijson
import json
from datetime import datetime
import os
from pathlib import Path
from typing import Dict, TextIO
import argparse
from collections import defaultdict


class EventSplitter:
    def __init__(self, input_file: str, output_dir: str):
        """
        Initialize the event splitter

        Args:
            input_file: Path to the large JSON input file
            output_dir: Directory where monthly files will be saved
        """
        self.input_file = input_file
        self.output_dir = Path(output_dir)
        self.file_handles: Dict[str, TextIO] = {}
        self.events_per_month = defaultdict(int)

    def _get_month_key(self, timestamp: int) -> str:
        """Convert Unix timestamp to month-year string"""
        date = datetime.fromtimestamp(timestamp)
        return f"{date.year}_{date.strftime('%b').lower()}"

    def _get_file_handle(self, month_key: str) -> TextIO:
        """Get or create file handle for a given month"""
        if month_key not in self.file_handles:
            filepath = self.output_dir / f"dvm_data_{month_key}.json"

            # Create directory if it doesn't exist
            self.output_dir.mkdir(parents=True, exist_ok=True)

            # Initialize the file with an opening bracket
            file_handle = open(filepath, "w", encoding="utf-8")
            file_handle.write("[\n")
            self.file_handles[month_key] = file_handle

        return self.file_handles[month_key]

    def process_file(self) -> None:
        """Process the input file and split events into monthly files"""
        try:
            with open(self.input_file, "rb") as input_file:
                # Create an iterator for the JSON array items
                parser = ijson.items(input_file, "item")

                for event in parser:
                    try:
                        month_key = self._get_month_key(event["created_at"])
                        file_handle = self._get_file_handle(month_key)

                        # Add comma if not the first event
                        if self.events_per_month[month_key] > 0:
                            file_handle.write(",\n")

                        # Write the event
                        json.dump(event, file_handle, indent=2)
                        self.events_per_month[month_key] += 1

                    except (KeyError, ValueError) as e:
                        print(f"Error processing event: {e}")
                        continue

        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """Close all file handles and finalize JSON files"""
        for file_handle in self.file_handles.values():
            # Add closing bracket
            file_handle.write("\n]")
            file_handle.close()

    def print_summary(self) -> None:
        """Print summary of events processed per month"""
        print("\nProcessing complete! Summary of events per month:")
        for month, count in sorted(self.events_per_month.items()):
            print(f"dvm_data_{month}.json: {count:,} events")


def main():
    parser = argparse.ArgumentParser(
        description="Split large JSON event file into monthly files"
    )
    parser.add_argument("input_file", help="Path to the input JSON file")
    parser.add_argument(
        "--output-dir", default="output", help="Directory for output files"
    )

    args = parser.parse_args()

    splitter = EventSplitter(args.input_file, args.output_dir)
    print(f"Processing {args.input_file}...")
    splitter.process_file()
    splitter.print_summary()


if __name__ == "__main__":
    main()
