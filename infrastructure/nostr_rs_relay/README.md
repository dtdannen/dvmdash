# nostr-rs-relay

Nostr-rs-relay is a reliable, efficient relay and in the Dockerfile here, we simply clone the current public repo from https://github.com/scsibug/nostr-rs-relay and then run it with a custom configuration, so that it is focused only on DVM related activity. This means focusing on kinds:

- 5000-7000
- 31990
- 0  # nostr-sdk python library yells at us if it can't get this one from the relay, so we include it


