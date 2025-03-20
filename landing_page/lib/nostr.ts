import NDK from '@nostr-dev-kit/ndk';
import { nip19 } from 'nostr-tools';

// Configure relays
const relays = [
  'wss://relay.damus.io',
  'wss://relay.primal.net'
];

// Initialize NDK
export const ndk = new NDK({ explicitRelayUrls: relays });

// Decode bech32 note IDs to hex
export function decodeNoteId(noteId: string): string {
  if (noteId.startsWith('note1')) {
    try {
      const { data } = nip19.decode(noteId);
      return data as string;
    } catch (e) {
      console.error('Failed to decode note ID:', e);
      return '';
    }
  }
  return noteId; // Already in hex format
}

// Decode naddr to get event coordinates
export function decodeNaddr(naddr: string): { kind: number, pubkey: string, identifier: string } | null {
  if (naddr.startsWith('naddr1')) {
    try {
      const { data } = nip19.decode(naddr);
      return data as { kind: number, pubkey: string, identifier: string };
    } catch (e) {
      console.error('Failed to decode naddr:', e);
      return null;
    }
  }
  return null;
}

// Fetch events by their IDs (accepts both bech32 and hex formats)
export async function fetchEventsByIds(noteIds: string[]) {
  await ndk.connect();
  
  // Decode any bech32 IDs to hex
  const hexIds = noteIds.map(decodeNoteId).filter(id => id !== '');
  
  if (hexIds.length === 0) return [];
  
  const filter = { ids: hexIds };
  const events = await ndk.fetchEvents(filter);
  
  return Array.from(events);
}

// Fetch events by naddr identifiers
export async function fetchEventsByNaddrs(naddrs: string[]) {
  await ndk.connect();
  
  const events = [];
  
  for (const naddr of naddrs) {
    const decoded = decodeNaddr(naddr);
    if (decoded) {
      const { kind, pubkey, identifier } = decoded;
      const filter = { 
        kinds: [kind],
        authors: [pubkey],
        '#d': [identifier]
      };
      
      const fetchedEvents = await ndk.fetchEvents(filter);
      events.push(...Array.from(fetchedEvents));
    }
  }
  
  return events;
}

// Manual category overrides for specific event IDs
const categoryOverrides: Record<string, string> = {
  // Example: Map specific event IDs to categories
  // 'hex_event_id_1': 'tutorial',
  // 'hex_event_id_2': 'news',
};

// Convert Nostr event to Article format
export function eventToArticle(event: any) {
  // Extract title from tags or first line of content
  const titleTag = event.tags.find((t: string[]) => t[0] === 'title');
  const title = titleTag ? titleTag[1] : event.content.split('\n')[0].substring(0, 60);
  
  // Extract author
  const authorTag = event.tags.find((t: string[]) => t[0] === 'p');
  const author = authorTag ? authorTag[1].substring(0, 8) + '...' : event.pubkey.substring(0, 8) + '...';
  
  // Extract description (first 150 chars of content)
  const description = event.content.substring(0, 150) + (event.content.length > 150 ? '...' : '');
  
  // Extract image URL from tags
  const imageTag = event.tags.find((t: string[]) => t[0] === 'image');
  const imageUrl = imageTag ? imageTag[1] : undefined;
  
  // Generate naddr for the event
  const dTag = event.tags.find((t: string[]) => t[0] === 'd')?.[1] || '';
  const naddr = generateNaddr(event.kind, event.pubkey, dTag, event);
  
  // Check if we have a manual category override for this event
  if (categoryOverrides[event.id]) {
    return {
      title,
      author,
      url: `https://habla.news/a/${naddr}`,
      description,
      category: categoryOverrides[event.id],
      readTime: calculateReadTime(event.content),
      imageUrl,
      naddr,
      nostrEvent: event // Keep the original event for reference
    };
  }
  
  // Determine category from tags
  const categoryTag = event.tags.find((t: string[]) => t[0] === 'c' || t[0] === 'category');
  let category = 'misc';
  
  // Map to our preferred categories
  if (categoryTag) {
    const tagValue = categoryTag[1].toLowerCase();
    if (tagValue.includes('tutorial') || tagValue.includes('guide') || tagValue.includes('how-to')) {
      category = 'tutorial';
    } else if (tagValue.includes('news') || tagValue.includes('update') || tagValue.includes('announcement')) {
      category = 'news';
    }
  }
  
  return {
    title,
    author,
    url: `https://habla.news/a/${naddr}`,
    primalUrl: `https://primal.net/a/${naddr}`, // Add Primal URL
    description,
    category,
    readTime: calculateReadTime(event.content),
    imageUrl,
    naddr,
    createdAt: event.created_at, // Add creation timestamp for sorting
    nostrEvent: event // Keep the original event for reference
  };
}

// Generate naddr for an event
function generateNaddr(kind: number, pubkey: string, dTag: string, event?: any): string {
  try {
    // Use the existing naddr from the event if available
    if (event && event.tags) {
      const altTag = event.tags.find((t: string[]) => t[0] === 'alt');
      if (altTag && altTag[1].startsWith('naddr1')) {
        return altTag[1];
      }
    }
    
    // Otherwise, encode the naddr using nip19
    return nip19.naddrEncode({
      kind,
      pubkey,
      identifier: dTag,
      relays: []
    });
  } catch (e) {
    console.error('Failed to generate naddr:', e);
    return '';
  }
}

// Helper function to calculate read time
function calculateReadTime(content: string): string {
  // Estimate read time (average reading speed: 200 words per minute)
  const wordCount = content.split(/\s+/).length;
  return Math.max(1, Math.ceil(wordCount / 200)) + ' min';
  
}
