# DVMDash Lite

A lightweight directory of Data Vending Machines (DVMs) on Nostr.

## Overview

DVMDash Lite is a streamlined version of DVMDash that fetches DVM profiles directly from Nostr relays without requiring any database or monitoring infrastructure. It showcases three categories of DVMs:

- **Legacy DVMs**: Original NIP-89 DVMs (kind 31990) supporting kinds 5000-7000
- **ContextVM Servers**: Modern context-aware virtual machines (kind 11316)
- **Encrypted DVMs**: Next-generation DVMs using NIP-17/NIP-EE encryption (kind 11999)

## Features

- **Zero Database**: Fetches all data directly from Nostr relays
- **Lightweight**: Single Next.js container, ~1GB RAM usage
- **Real-time**: Always shows current DVM profiles from the network
- **Educational**: Includes curated articles about DVMs

## Quick Start

### Using Docker Compose (Recommended)

```bash
docker compose up
```

Navigate to http://localhost:3000

### Local Development

```bash
npm install
npm run dev
```

## Architecture

- **Frontend**: Next.js 14 with App Router
- **Relay Communication**: @nostr-dev-kit/ndk for fetching events
- **Styling**: TailwindCSS with dark theme
- **Deployment**: Single Docker container

## Pages

- `/` - Homepage with navigation and sunset notice
- `/legacy-dvms` - Legacy DVM directory (kind 31990)
- `/context-dvms` - ContextVM server directory (kind 11316)
- `/encrypted-dvms` - Encrypted DVM directory (kind 11999)
- `/learn` - Educational articles about DVMs

## Environment Variables

No environment variables required! Everything fetches from public Nostr relays.

## Deployment

### Digital Ocean Droplet ($18/month)

```bash
# SSH into your droplet
ssh root@your-droplet-ip

# Clone the repo
git clone https://github.com/yourusername/dvmdash.git
cd dvmdash/dvmdash-lite

# Build and run
docker compose up -d

# View logs
docker compose logs -f
```

## Resource Requirements

- **RAM**: ~500MB-1GB
- **CPU**: 1-2 cores
- **Storage**: ~500MB
- **Network**: Outbound HTTPS to Nostr relays

## License

MIT

## Credits

Built for the Nostr community with ❤️
