import bech32


def hex_to_npub(hex_pubkey):
    hrp = "npub"  # Human-readable part for npub
    data = [int(hex_pubkey[i : i + 2], 16) for i in range(0, len(hex_pubkey), 2)]
    data = bech32.convertbits(data, 8, 5)
    npub = bech32.bech32_encode(hrp, data)
    return npub
