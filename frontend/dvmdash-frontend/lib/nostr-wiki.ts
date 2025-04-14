import NDK, { NDKEvent, NDKFilter } from '@nostr-dev-kit/ndk';
import { nip19 } from 'nostr-tools';

// Configure relays - using the same ones as in the publish script
const relays = [
  'wss://relay.damus.io',
  'wss://relay.primal.net',
  'wss://relay.wikifreedia.xyz'
];

// Initialize NDK
const ndk = new NDK({ explicitRelayUrls: relays });

/**
 * Fetch wiki event for a specific kind
 * @param kindNumber The kind number to fetch wiki for
 * @returns The most recent wiki event or null if none found
 */
export async function fetchWikiForKind(kindNumber: number): Promise<NDKEvent | null> {
  try {
    await ndk.connect();
    
    const filter: NDKFilter = {
      kinds: [30818],
      '#d': [`kind:${kindNumber}`]
    };
    
    const events = await ndk.fetchEvents(filter);
    const eventsArray = Array.from(events);
    
    // If multiple events exist, get the most recent one
    if (eventsArray.length > 0) {
      return eventsArray.sort((a: NDKEvent, b: NDKEvent) => b.created_at - a.created_at)[0];
    }
    
    return null;
  } catch (error) {
    console.error(`Error fetching wiki for kind ${kindNumber}:`, error);
    return null;
  }
}

/**
 * Extract human-readable title from wiki event
 * @param event The wiki event
 * @returns The human-readable title
 */
export function extractTitle(event: NDKEvent): string {
  const titleTag = event.tags.find((t: string[]) => t[0] === 'title');
  if (!titleTag || !titleTag[1]) return `Kind ${event.tags.find((t: string[]) => t[0] === 'd')?.[1].split(':')[1] || ''}`;
  
  // Remove "Nostr DVM" from the title
  const fullTitle = titleTag[1];
  return fullTitle.replace(/^Nostr DVM Kind \d+\/\d+ - /, '');
}

/**
 * Generate njump.me URL for a wiki event
 * @param event The wiki event
 * @returns The njump.me URL
 */
export function generateWikiUrl(event: NDKEvent): string {
  const dTag = event.tags.find((t: string[]) => t[0] === 'd')?.[1] || '';
  
  // Generate naddr
  const naddr = nip19.naddrEncode({
    kind: event.kind,
    pubkey: event.pubkey,
    identifier: dTag,
    relays: []
  });
  
  return `https://njump.me/${naddr}`;
}
