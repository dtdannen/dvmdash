import yaml
from pathlib import Path
from typing import Set, List
from enum import IntEnum
import logging

logger = logging.getLogger(__name__)


class EventKind(IntEnum):
    """Enum for common DVM event kinds"""

    DVM_NIP89_ANNOUNCEMENT = 31990
    DVM_FEEDBACK = 7000

    DVM_REQUEST_RANGE_START = 5000
    DVM_REQUEST_RANGE_END = 6000
    DVM_RESULT_RANGE_START = 6000
    DVM_RESULT_RANGE_END = 6999


def load_dvm_config() -> dict:
    """Load DVM configuration from YAML file"""
    config_path = Path(__file__).parent / "config" / "dvm_kinds.yaml"
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"DVM kinds config not found at {config_path}, using defaults")
        return {
            "known_kinds": [
                {"kind": EventKind.DVM_NIP89_ANNOUNCEMENT},
                {"kind": EventKind.DVM_FEEDBACK},
            ],
            "ranges": {
                "request": {
                    "start": EventKind.DVM_REQUEST_RANGE_START,
                    "end": EventKind.DVM_REQUEST_RANGE_END,
                },
                "result": {
                    "start": EventKind.DVM_RESULT_RANGE_START,
                    "end": EventKind.DVM_RESULT_RANGE_END,
                },
            },
            "excluded_kinds": [],
        }


def get_excluded_kinds() -> Set[int]:
    """Get set of excluded kind numbers"""
    config = load_dvm_config()
    excluded_kinds = {k["kind"] for k in config["excluded_kinds"]}

    for kind in excluded_kinds:
        if kind < 6000:
            if kind + 1000 not in excluded_kinds:
                excluded_kinds.add(kind + 1000)
        elif kind >= 6000:
            if kind - 1000 not in excluded_kinds:
                excluded_kinds.add(kind - 1000)

    return excluded_kinds


def get_relevant_kinds() -> List[int]:
    """Get list of all relevant DVM kind numbers"""
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
    excluded_kinds = get_excluded_kinds()

    # Combine all kinds and remove excluded ones
    all_kinds = set(known_kinds + list(request_range) + list(result_range))

    return list(all_kinds - excluded_kinds)


def is_dvm_kind(kind: int) -> bool:
    """Check if a kind number is a valid DVM kind"""
    return kind in get_relevant_kinds()


def is_dvm_request(kind: int) -> bool:
    """Check if a kind number is in the DVM request range and not excluded"""
    return (
        EventKind.DVM_REQUEST_RANGE_START <= kind < EventKind.DVM_REQUEST_RANGE_END
        and kind not in get_excluded_kinds()
    )


def is_dvm_result(kind: int) -> bool:
    """Check if a kind number is in the DVM result range"""
    return (
        EventKind.DVM_RESULT_RANGE_START <= kind < EventKind.DVM_RESULT_RANGE_END
        and kind not in get_excluded_kinds()
    )
