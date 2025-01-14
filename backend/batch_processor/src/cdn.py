import os
import json
import asyncio
from datetime import datetime
from typing import List, Dict, AsyncGenerator
import boto3  # DigitalOcean Spaces uses the S3 protocol
from botocore.client import Config
from loguru import logger


class SpacesEventArchiver:
    def __init__(
        self,
        space_name: str,
        space_region: str,
        spaces_key: str,
        spaces_secret: str,
        chunk_size: int = 100 * 1024 * 1024,  # 100MB chunks
        batch_size: int = 1000,
    ):  # Number of events to process at once
        """
        Initialize a DigitalOcean Spaces archiver for events.

        Args:
            space_name: Name of your DigitalOcean Space
            space_region: Region of your Space (e.g., 'nyc3', 'sfo2')
            spaces_key: DigitalOcean Spaces access key
            spaces_secret: DigitalOcean Spaces secret
            chunk_size: Maximum size of each archive file in bytes
            batch_size: Number of events to fetch from database at once
        """
        self.space_name = space_name
        self.chunk_size = chunk_size
        self.batch_size = batch_size

        # Configure spaces client
        spaces_endpoint = f"https://{space_region}.digitaloceanspaces.com"
        self.spaces_client = boto3.client(
            "s3",
            endpoint_url=spaces_endpoint,
            region_name=space_region,
            aws_access_key_id=spaces_key,
            aws_secret_access_key=spaces_secret,
            config=Config(signature_version="s3v4"),
        )

        # Store base URL for constructing file URLs
        self.base_url = f"https://{space_name}.{space_region}.digitaloceanspaces.com"

    async def archive_month_events(
        self, conn, year_month: str, start_timestamp: datetime, end_timestamp: datetime
    ) -> List[Dict]:
        """
        Archive events for a specific month to DigitalOcean Spaces.
        Returns list of archive information including URLs and sizes.
        """
        archives = []
        current_chunk = []
        current_chunk_size = 0
        chunk_number = 1

        logger.info(f"Starting archive process for {year_month}")

        async for event_batch in self._fetch_events_generator(
            conn, start_timestamp, end_timestamp
        ):
            for event in event_batch:
                # Convert event to JSON string to calculate its size
                event_json = json.dumps(event)
                event_size = len(event_json.encode("utf-8"))

                # If adding this event would exceed chunk size, upload current chunk
                if current_chunk_size + event_size > self.chunk_size and current_chunk:
                    archive_info = await self._upload_chunk(
                        year_month, chunk_number, current_chunk
                    )
                    archives.append(archive_info)
                    chunk_number += 1
                    current_chunk = []
                    current_chunk_size = 0

                current_chunk.append(event)
                current_chunk_size += event_size

        # Upload any remaining events in the last chunk
        if current_chunk:
            archive_info = await self._upload_chunk(
                year_month, chunk_number, current_chunk
            )
            archives.append(archive_info)

        logger.info(f"Completed archiving {len(archives)} chunks for {year_month}")
        return archives

    async def _fetch_events_generator(
        self, conn, start_timestamp: datetime, end_timestamp: datetime
    ) -> AsyncGenerator[List[Dict], None]:
        """
        Generator that yields batches of events to process.
        """
        last_id = 0
        total_events = 0

        while True:
            events = await conn.fetch(
                """
                SELECT id, pubkey, created_at, kind, content, sig, tags, raw_data
                FROM raw_events
                WHERE id > $1 
                AND created_at >= $2 
                AND created_at < $3
                ORDER BY id
                LIMIT $4
            """,
                last_id,
                start_timestamp,
                end_timestamp,
                self.batch_size,
            )

            if not events:
                break

            # Update last_id for next iteration
            last_id = events[-1]["id"]

            # Convert to list of dicts and ensure proper datetime handling
            event_dicts = []
            for event in events:
                event_dict = dict(event)
                # Convert datetime to timestamp integer
                if isinstance(event_dict["created_at"], datetime):
                    event_dict["created_at"] = int(event_dict["created_at"].timestamp())
                event_dicts.append(event_dict)

            total_events += len(event_dicts)
            logger.debug(
                f"Fetched batch of {len(event_dicts)} events. Total so far: {total_events}"
            )

            yield event_dicts

    async def _upload_chunk(
        self, year_month: str, chunk_number: int, events: List[Dict]
    ) -> Dict:
        """
        Upload a chunk of events to DigitalOcean Spaces.
        Returns information about the uploaded chunk.
        """
        # Create file path like: events/2024-01/chunk_001.json
        file_name = f"chunk_{str(chunk_number).zfill(3)}.json"
        file_path = f"events/{year_month}/{file_name}"

        # Convert events to JSON
        json_data = json.dumps(events, ensure_ascii=False)
        data_bytes = json_data.encode("utf-8")

        # Upload to Spaces
        try:
            self.spaces_client.put_object(
                Bucket=self.space_name,
                Key=file_path,
                Body=data_bytes,
                ContentType="application/json",
                ACL="private",
            )

            # Return information about the uploaded chunk
            return {
                "file_name": file_name,
                "file_path": file_path,
                "url": f"{self.base_url}/{file_path}",
                "size_bytes": len(data_bytes),
                "event_count": len(events),
                "chunk_number": chunk_number,
            }

        except Exception as e:
            logger.error(f"Error uploading chunk to Spaces: {e}")
            raise

    async def create_month_manifest(self, year_month: str, archives: List[Dict]) -> str:
        """
        Create a manifest file listing all chunks for the month.
        Returns the manifest URL.
        """
        manifest = {
            "year_month": year_month,
            "created_at": datetime.utcnow().isoformat(),
            "archives": archives,
            "total_files": len(archives),
            "total_size_bytes": sum(archive["size_bytes"] for archive in archives),
            "total_events": sum(archive["event_count"] for archive in archives),
        }

        manifest_path = f"events/{year_month}/manifest.json"

        # Upload manifest to Spaces
        self.spaces_client.put_object(
            Bucket=self.space_name,
            Key=manifest_path,
            Body=json.dumps(manifest, indent=2).encode("utf-8"),
            ContentType="application/json",
            ACL="private",
        )

        manifest_url = f"{self.base_url}/{manifest_path}"
        logger.info(f"Created manifest at {manifest_url}")
        return manifest_url
