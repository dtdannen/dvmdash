#!/usr/bin/env python3
"""
Extract historical DVMDash data for the lite archive.

This script connects to the production PostgreSQL database and extracts
all metrics needed for the dvmdash-lite historical page.

Usage:
    1. Create a .env file in the scripts/ directory with:
       DATABASE_URL=postgresql://user:pass@host:port/dbname

    2. Run: python extract_historical_data.py

    3. Output: dvmdash_historical.json
"""

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")


def decimal_default(obj):
    """JSON serializer for Decimal types."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def extract_profile_info(profile_data) -> dict:
    """Safely extract profile info from various profile data structures."""
    result = {"name": None, "nip05": None, "about": None, "picture": None}

    if not profile_data:
        return result

    try:
        profile = profile_data
        if isinstance(profile, str):
            profile = json.loads(profile)

        # Handle list format (array of events)
        if isinstance(profile, list):
            if len(profile) > 0:
                profile = profile[0]  # Take first event
            else:
                return result

        # Now profile should be a dict
        if not isinstance(profile, dict):
            return result

        # Try to get content - could be at top level or nested
        content = profile.get("content")

        # If content is a string, parse it
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                content = None

        # If no content field, maybe the profile IS the content
        if not content and "name" in profile:
            content = profile

        if content and isinstance(content, dict):
            result["name"] = content.get("name") or content.get("display_name")
            result["nip05"] = content.get("nip05")
            result["about"] = content.get("about")
            result["picture"] = content.get("picture")

    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        pass

    return result


def get_connection():
    """Create database connection."""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def extract_totals(cursor) -> dict:
    """Section 1: The Big Numbers (Hero Stats)"""
    print("Extracting totals...")

    # Total DVMs
    cursor.execute("SELECT COUNT(*) as count FROM dvms")
    total_dvms = cursor.fetchone()["count"]

    # Total users (non-DVM)
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_dvm = FALSE")
    total_users = cursor.fetchone()["count"]

    # Total unique kinds
    cursor.execute("SELECT COUNT(DISTINCT kind) as count FROM kind_dvm_support")
    total_kinds = cursor.fetchone()["count"]

    # Total requests and responses from monthly_activity
    cursor.execute("""
        SELECT
            COALESCE(SUM(total_requests), 0) as total_requests,
            COALESCE(SUM(total_responses), 0) as total_responses
        FROM monthly_activity
    """)
    activity = cursor.fetchone()

    # Monitoring period
    cursor.execute("SELECT MIN(first_seen) as first, MAX(last_seen) as last FROM dvms")
    period = cursor.fetchone()

    return {
        "total_dvms": total_dvms,
        "total_users": total_users,
        "total_kinds": total_kinds,
        "total_requests": activity["total_requests"],
        "total_responses": activity["total_responses"],
        "monitoring_start": period["first"],
        "monitoring_end": period["last"],
    }


def extract_monthly_activity(cursor) -> list:
    """Section 2: Growth Over Time - Monthly aggregates"""
    print("Extracting monthly activity...")

    cursor.execute("""
        SELECT
            year_month,
            total_requests,
            total_responses,
            unique_dvms,
            unique_kinds,
            unique_users,
            dvm_activity,
            kind_activity
        FROM monthly_activity
        ORDER BY year_month ASC
    """)

    rows = cursor.fetchall()

    # Calculate cumulative totals
    cumulative_dvms = 0
    cumulative_users = 0
    cumulative_requests = 0
    cumulative_responses = 0

    result = []
    for row in rows:
        cumulative_requests += row["total_requests"]
        cumulative_responses += row["total_responses"]

        result.append({
            "month": row["year_month"],
            "requests": row["total_requests"],
            "responses": row["total_responses"],
            "unique_dvms": row["unique_dvms"],
            "unique_kinds": row["unique_kinds"],
            "unique_users": row["unique_users"],
            "cumulative_requests": cumulative_requests,
            "cumulative_responses": cumulative_responses,
        })

    return result


def extract_cumulative_dvms(cursor) -> list:
    """Calculate cumulative DVM count over time by first_seen date."""
    print("Extracting cumulative DVM growth...")

    cursor.execute("""
        SELECT
            TO_CHAR(first_seen, 'YYYY-MM') as month,
            COUNT(*) as new_dvms
        FROM dvms
        GROUP BY TO_CHAR(first_seen, 'YYYY-MM')
        ORDER BY month ASC
    """)

    rows = cursor.fetchall()

    cumulative = 0
    result = []
    for row in rows:
        cumulative += row["new_dvms"]
        result.append({
            "month": row["month"],
            "new_dvms": row["new_dvms"],
            "cumulative_dvms": cumulative,
        })

    return result


def extract_cumulative_users(cursor) -> list:
    """Calculate cumulative user count over time by first_seen date."""
    print("Extracting cumulative user growth...")

    cursor.execute("""
        SELECT
            TO_CHAR(first_seen, 'YYYY-MM') as month,
            COUNT(*) as new_users
        FROM users
        WHERE is_dvm = FALSE
        GROUP BY TO_CHAR(first_seen, 'YYYY-MM')
        ORDER BY month ASC
    """)

    rows = cursor.fetchall()

    cumulative = 0
    result = []
    for row in rows:
        cumulative += row["new_users"]
        result.append({
            "month": row["month"],
            "new_users": row["new_users"],
            "cumulative_users": cumulative,
        })

    return result


def extract_top_dvms(cursor, limit: int = 50) -> list:
    """Section 3: Top DVMs by total responses"""
    print(f"Extracting top {limit} DVMs...")

    cursor.execute("""
        SELECT
            d.id,
            d.first_seen,
            d.last_seen,
            d.last_profile_event_raw_json,
            COALESCE(SUM(dts.total_responses), 0) as total_responses,
            COALESCE(SUM(dts.total_feedback), 0) as total_feedback
        FROM dvms d
        LEFT JOIN dvm_time_window_stats dts ON d.id = dts.dvm_id AND dts.window_size = '30 days'
        GROUP BY d.id, d.first_seen, d.last_seen, d.last_profile_event_raw_json
        ORDER BY total_responses DESC
        LIMIT %s
    """, (limit,))

    rows = cursor.fetchall()

    result = []
    for row in rows:
        profile_info = extract_profile_info(row["last_profile_event_raw_json"])

        result.append({
            "id": row["id"],
            "name": profile_info["name"],
            "nip05": profile_info["nip05"],
            "about": profile_info["about"][:200] if profile_info["about"] else None,
            "picture": profile_info["picture"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "total_responses": row["total_responses"],
            "total_feedback": row["total_feedback"],
        })

    return result


def extract_founding_dvms(cursor) -> list:
    """DVMs that were active in 2023 and are still around."""
    print("Extracting founding DVMs (2023 pioneers)...")

    cursor.execute("""
        SELECT
            d.id,
            d.first_seen,
            d.last_seen,
            d.last_profile_event_raw_json,
            EXTRACT(DAY FROM (d.last_seen - d.first_seen)) as days_active
        FROM dvms d
        WHERE d.first_seen < '2024-01-01'
        AND d.last_seen > '2024-06-01'
        ORDER BY d.first_seen ASC
    """)

    rows = cursor.fetchall()

    result = []
    for row in rows:
        profile_info = extract_profile_info(row["last_profile_event_raw_json"])

        result.append({
            "id": row["id"],
            "name": profile_info["name"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "days_active": int(row["days_active"]) if row["days_active"] else 0,
        })

    return result


def extract_dvm_timeline(cursor) -> list:
    """When each DVM first appeared."""
    print("Extracting DVM timeline...")

    cursor.execute("""
        SELECT
            id,
            first_seen,
            last_profile_event_raw_json
        FROM dvms
        ORDER BY first_seen ASC
    """)

    rows = cursor.fetchall()

    result = []
    for row in rows:
        profile_info = extract_profile_info(row["last_profile_event_raw_json"])

        result.append({
            "id": row["id"],
            "name": profile_info["name"],
            "first_seen": row["first_seen"],
        })

    return result


def extract_top_kinds(cursor, limit: int = 30) -> list:
    """Section 4: Top kinds by request volume and DVM support."""
    print(f"Extracting top {limit} kinds...")

    # Get kinds with most DVM support
    cursor.execute("""
        SELECT
            kind,
            COUNT(DISTINCT dvm) as dvm_count,
            MIN(first_seen) as first_seen,
            MAX(last_seen) as last_seen
        FROM kind_dvm_support
        GROUP BY kind
        ORDER BY dvm_count DESC
        LIMIT %s
    """, (limit,))

    kind_support = {row["kind"]: dict(row) for row in cursor.fetchall()}

    # Get request/response totals from monthly_activity
    cursor.execute("""
        SELECT
            year_month,
            kind_activity
        FROM monthly_activity
        ORDER BY year_month
    """)

    kind_totals = {}
    for row in cursor.fetchall():
        if row["kind_activity"]:
            for ka in row["kind_activity"]:
                kind = ka.get("kind")
                if kind:
                    if kind not in kind_totals:
                        kind_totals[kind] = {"requests": 0, "responses": 0}
                    kind_totals[kind]["requests"] += ka.get("request_count", 0)
                    kind_totals[kind]["responses"] += ka.get("response_count", 0)

    # Combine data
    all_kinds = set(kind_support.keys()) | set(kind_totals.keys())

    result = []
    for kind in all_kinds:
        support = kind_support.get(kind, {})
        totals = kind_totals.get(kind, {"requests": 0, "responses": 0})

        result.append({
            "kind": kind,
            "dvm_count": support.get("dvm_count", 0),
            "total_requests": totals["requests"],
            "total_responses": totals["responses"],
            "first_seen": support.get("first_seen"),
            "last_seen": support.get("last_seen"),
        })

    # Sort by total requests
    result.sort(key=lambda x: x["total_requests"], reverse=True)

    return result[:limit]


def extract_kind_timeline(cursor) -> list:
    """When each kind first appeared."""
    print("Extracting kind adoption timeline...")

    cursor.execute("""
        SELECT
            kind,
            MIN(first_seen) as first_seen,
            COUNT(DISTINCT dvm) as dvm_count
        FROM kind_dvm_support
        GROUP BY kind
        ORDER BY first_seen ASC
    """)

    return [dict(row) for row in cursor.fetchall()]


def extract_ecosystem_health(cursor) -> dict:
    """Section 5: Ecosystem health indicators over time."""
    print("Extracting ecosystem health metrics...")

    # Response rate over time (from monthly_activity)
    cursor.execute("""
        SELECT
            year_month,
            total_requests,
            total_responses,
            unique_dvms,
            unique_kinds,
            CASE
                WHEN total_requests > 0
                THEN ROUND(total_responses::numeric / total_requests * 100, 2)
                ELSE 0
            END as response_rate
        FROM monthly_activity
        ORDER BY year_month ASC
    """)

    monthly_health = [dict(row) for row in cursor.fetchall()]

    # Average DVMs per kind (decentralization metric)
    cursor.execute("""
        SELECT
            AVG(dvm_count) as avg_dvms_per_kind
        FROM (
            SELECT kind, COUNT(DISTINCT dvm) as dvm_count
            FROM kind_dvm_support
            GROUP BY kind
        ) sub
    """)
    avg_dvms_per_kind = cursor.fetchone()["avg_dvms_per_kind"]

    return {
        "monthly_health": monthly_health,
        "avg_dvms_per_kind": float(avg_dvms_per_kind) if avg_dvms_per_kind else 0,
    }


def extract_milestones(cursor) -> list:
    """Notable milestones in the ecosystem."""
    print("Extracting milestones...")

    milestones = []

    # First DVM
    cursor.execute("SELECT id, first_seen FROM dvms ORDER BY first_seen ASC LIMIT 1")
    first = cursor.fetchone()
    if first:
        milestones.append({
            "date": first["first_seen"],
            "event": "first_dvm",
            "description": "First DVM appeared",
            "dvm_id": first["id"],
        })

    # 10th, 50th, 100th DVM
    for n in [10, 50, 100, 200, 500]:
        cursor.execute(f"""
            SELECT id, first_seen
            FROM dvms
            ORDER BY first_seen ASC
            LIMIT 1 OFFSET {n - 1}
        """)
        row = cursor.fetchone()
        if row:
            milestones.append({
                "date": row["first_seen"],
                "event": f"dvm_{n}",
                "description": f"{n}th DVM joined",
                "dvm_id": row["id"],
            })

    # Peak activity month
    cursor.execute("""
        SELECT year_month, total_requests, total_responses
        FROM monthly_activity
        ORDER BY total_requests DESC
        LIMIT 1
    """)
    peak = cursor.fetchone()
    if peak:
        milestones.append({
            "date": f"{peak['year_month']}-01",
            "event": "peak_activity",
            "description": f"Peak activity month: {peak['total_requests']} requests, {peak['total_responses']} responses",
        })

    # Sort by date
    milestones.sort(key=lambda x: str(x["date"]))

    return milestones


def extract_relay_data(cursor) -> dict:
    """Extract relay usage data from raw_events tags."""
    print("Extracting relay data (this may take a while)...")

    # Extract all unique relays and their first appearance
    # Relays appear in tags as ["relay", "wss://..."] or within "relays" tags
    cursor.execute("""
        WITH relay_extractions AS (
            SELECT
                created_at,
                pubkey,
                kind,
                tag->>1 as relay_url
            FROM raw_events,
            jsonb_array_elements(tags) as tag
            WHERE tag->>0 IN ('relay', 'relays')
            AND tag->>1 IS NOT NULL
            AND tag->>1 LIKE 'wss://%' OR tag->>1 LIKE 'ws://%'
        )
        SELECT
            relay_url,
            MIN(created_at) as first_seen,
            MAX(created_at) as last_seen,
            COUNT(*) as usage_count,
            COUNT(DISTINCT pubkey) as unique_users
        FROM relay_extractions
        GROUP BY relay_url
        ORDER BY usage_count DESC
    """)

    all_relays = [dict(row) for row in cursor.fetchall()]
    print(f"  Found {len(all_relays)} unique relays")

    # Top relays by usage
    top_relays = all_relays[:100]

    # Relay growth over time (monthly)
    print("  Extracting relay growth over time...")
    cursor.execute("""
        WITH relay_extractions AS (
            SELECT
                created_at,
                tag->>1 as relay_url
            FROM raw_events,
            jsonb_array_elements(tags) as tag
            WHERE tag->>0 IN ('relay', 'relays')
            AND tag->>1 IS NOT NULL
            AND (tag->>1 LIKE 'wss://%' OR tag->>1 LIKE 'ws://%')
        ),
        relay_first_seen AS (
            SELECT
                relay_url,
                MIN(created_at) as first_seen
            FROM relay_extractions
            GROUP BY relay_url
        )
        SELECT
            TO_CHAR(first_seen, 'YYYY-MM') as month,
            COUNT(*) as new_relays
        FROM relay_first_seen
        GROUP BY TO_CHAR(first_seen, 'YYYY-MM')
        ORDER BY month ASC
    """)

    relay_growth_raw = cursor.fetchall()
    cumulative = 0
    relay_growth = []
    for row in relay_growth_raw:
        cumulative += row["new_relays"]
        relay_growth.append({
            "month": row["month"],
            "new_relays": row["new_relays"],
            "cumulative_relays": cumulative,
        })

    # Relays used by DVMs vs Users
    print("  Extracting relay usage by entity type...")
    cursor.execute("""
        WITH relay_extractions AS (
            SELECT
                pubkey,
                kind,
                tag->>1 as relay_url
            FROM raw_events,
            jsonb_array_elements(tags) as tag
            WHERE tag->>0 IN ('relay', 'relays')
            AND tag->>1 IS NOT NULL
            AND (tag->>1 LIKE 'wss://%' OR tag->>1 LIKE 'ws://%')
        ),
        dvm_relays AS (
            SELECT DISTINCT relay_url
            FROM relay_extractions re
            WHERE EXISTS (SELECT 1 FROM dvms d WHERE d.id = re.pubkey)
            OR re.kind BETWEEN 6000 AND 6999
        ),
        user_relays AS (
            SELECT DISTINCT relay_url
            FROM relay_extractions re
            WHERE re.kind BETWEEN 5000 AND 5999
            AND NOT EXISTS (SELECT 1 FROM dvms d WHERE d.id = re.pubkey)
        )
        SELECT
            (SELECT COUNT(*) FROM dvm_relays) as dvm_relay_count,
            (SELECT COUNT(*) FROM user_relays) as user_relay_count,
            (SELECT COUNT(*) FROM dvm_relays WHERE relay_url IN (SELECT relay_url FROM user_relays)) as shared_relay_count
    """)

    relay_by_type = cursor.fetchone()

    # Top relays used by DVMs
    print("  Extracting top DVM relays...")
    cursor.execute("""
        WITH relay_extractions AS (
            SELECT
                pubkey,
                kind,
                tag->>1 as relay_url
            FROM raw_events,
            jsonb_array_elements(tags) as tag
            WHERE tag->>0 IN ('relay', 'relays')
            AND tag->>1 IS NOT NULL
            AND (tag->>1 LIKE 'wss://%' OR tag->>1 LIKE 'ws://%')
            AND (
                EXISTS (SELECT 1 FROM dvms d WHERE d.id = raw_events.pubkey)
                OR kind BETWEEN 6000 AND 6999
            )
        )
        SELECT
            relay_url,
            COUNT(*) as usage_count,
            COUNT(DISTINCT pubkey) as unique_dvms
        FROM relay_extractions
        GROUP BY relay_url
        ORDER BY unique_dvms DESC
        LIMIT 50
    """)

    top_dvm_relays = [dict(row) for row in cursor.fetchall()]

    # Top relays used by Users (requesters)
    print("  Extracting top user relays...")
    cursor.execute("""
        WITH relay_extractions AS (
            SELECT
                pubkey,
                tag->>1 as relay_url
            FROM raw_events,
            jsonb_array_elements(tags) as tag
            WHERE tag->>0 IN ('relay', 'relays')
            AND tag->>1 IS NOT NULL
            AND (tag->>1 LIKE 'wss://%' OR tag->>1 LIKE 'ws://%')
            AND kind BETWEEN 5000 AND 5999
            AND NOT EXISTS (SELECT 1 FROM dvms d WHERE d.id = raw_events.pubkey)
        )
        SELECT
            relay_url,
            COUNT(*) as usage_count,
            COUNT(DISTINCT pubkey) as unique_users
        FROM relay_extractions
        GROUP BY relay_url
        ORDER BY unique_users DESC
        LIMIT 50
    """)

    top_user_relays = [dict(row) for row in cursor.fetchall()]

    return {
        "total_unique_relays": len(all_relays),
        "top_relays": top_relays,
        "relay_growth": relay_growth,
        "relay_by_entity_type": {
            "dvm_relays": relay_by_type["dvm_relay_count"],
            "user_relays": relay_by_type["user_relay_count"],
            "shared_relays": relay_by_type["shared_relay_count"],
        },
        "top_dvm_relays": top_dvm_relays,
        "top_user_relays": top_user_relays,
    }


def main():
    print("=" * 60)
    print("DVMDash Historical Data Extraction")
    print("=" * 60)
    print()

    conn = get_connection()
    cursor = conn.cursor()

    try:
        data = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "description": "Historical DVMDash data archive - chronicling the first 2.5 years of DVMs on Nostr (July 2023 - November 2025)",
            },
            "totals": extract_totals(cursor),
            "monthly_activity": extract_monthly_activity(cursor),
            "dvm_growth": extract_cumulative_dvms(cursor),
            "user_growth": extract_cumulative_users(cursor),
            "top_dvms": extract_top_dvms(cursor),
            "founding_dvms": extract_founding_dvms(cursor),
            "dvm_timeline": extract_dvm_timeline(cursor),
            "top_kinds": extract_top_kinds(cursor),
            "kind_timeline": extract_kind_timeline(cursor),
            "ecosystem_health": extract_ecosystem_health(cursor),
            "milestones": extract_milestones(cursor),
            "relay_data": extract_relay_data(cursor),
        }

        # Write output
        output_file = "dvmdash_historical.json"
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2, default=decimal_default)

        print()
        print("=" * 60)
        print(f"Success! Data written to {output_file}")
        print("=" * 60)
        print()
        print("Summary:")
        print(f"  - Total DVMs: {data['totals']['total_dvms']}")
        print(f"  - Total Users: {data['totals']['total_users']}")
        print(f"  - Total Requests: {data['totals']['total_requests']}")
        print(f"  - Total Responses: {data['totals']['total_responses']}")
        print(f"  - Months of data: {len(data['monthly_activity'])}")
        print(f"  - Top DVMs captured: {len(data['top_dvms'])}")
        print(f"  - Kinds tracked: {len(data['top_kinds'])}")
        print(f"  - Unique relays discovered: {data['relay_data']['total_unique_relays']}")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
