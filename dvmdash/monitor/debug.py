"""
Contains all the logic to handling debugging for the user
"""
import helpers
import re


def debug_guess(s):
    """
    s: str - passed in from the user. can be anything nostr related
    """

    # start checking for many cases

    if has_pub_key(s):
        return "pub_key"

    if has_kind_num(s):
        return "kind_num"

    if has_event_id(s):
        return "event_id"


def has_pub_keys(s):
    """
    s: str - passed in from the user. can be anything nostr related
    """

    # key is the npub, value is another dict that contains useful data like the hex key, profile info, etc.
    npubs_data = {}

    npub_regex = r"npub1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{58}"

    matches = re.findall(npub_regex, s)

    for match in matches:
        npubs_data[match] = {"hex_pubkey": helpers.npub_to_hex(match)}

    npub_hex_regex = r"[0-9a-f]{64}"

    matches = re.findall(npub_hex_regex, s)

    for match in matches:
        npubs_data[helpers.hex_to_npub(match)] = {"hex_pubkey": match}

    return npubs_data


def has_kind_num(s):
    """
    s: str - passed in from the user. can be anything nostr related
    """

    kind_num_regex = r"kind\d+"

    matches = re.findall(kind_num_regex, s)

    return matches
