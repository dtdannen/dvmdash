import bech32
import json
from bson import ObjectId


def hex_to_npub(hex_pubkey):
    hrp = "npub"  # Human-readable part for npub
    data = [int(hex_pubkey[i : i + 2], 16) for i in range(0, len(hex_pubkey), 2)]
    data = bech32.convertbits(data, 8, 5)
    npub = bech32.bech32_encode(hrp, data)
    return npub


def sanitize_json(data):
    if isinstance(data, dict):
        sanitized_dict = {}
        for k, v in data.items():
            if isinstance(v, (str, int, float, bool, type(None))):
                sanitized_dict[k] = v
            else:
                sanitized_dict[k] = str(v)
        return sanitized_dict
    else:
        return str(data)


def clean_for_json(data):
    if isinstance(data, dict):
        return {k: clean_for_json(v) for k, v in data.items() if k != "_id"}
    elif isinstance(data, list):
        return [clean_for_json(i) for i in data]
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data
