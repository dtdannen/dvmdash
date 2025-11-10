import NDK, { NDKEvent, NDKFilter } from '@nostr-dev-kit/ndk';
import { nip19 } from 'nostr-tools';

// Configure relays - using reliable ones
const relays = [
  'wss://relay.damus.io',
  'wss://relay.primal.net',
  'wss://nos.lol',
  'wss://relay.snort.social'
];

// Initialize NDK with configuration to prevent hanging
export const ndk = new NDK({ 
  explicitRelayUrls: relays,
  enableOutboxModel: false,
});

// Connect with timeout
const connectionTimeout = setTimeout(() => {
  console.warn('NDK connection taking longer than expected, but will continue trying...');
}, 5000);

ndk.connect().then(() => {
  clearTimeout(connectionTimeout);
  console.log('NDK connected to relays');
}).catch((err) => {
  clearTimeout(connectionTimeout);
  console.error('NDK connection error:', err);
});

// Cache for profile metadata to avoid redundant requests
const profileCache: Record<string, any> = {};
const CACHE_EXPIRY = 24 * 60 * 60 * 1000; // 24 hours

interface CachedProfile {
  data: any;
  timestamp: number;
}

// Decode naddr to get event coordinates
export function decodeNaddr(naddr: string): { kind: number, pubkey: string, identifier: string } | null {
  if (!naddr || typeof naddr !== 'string') {
    console.error('Invalid naddr provided:', naddr);
    return null;
  }

  if (naddr.startsWith('naddr1')) {
    try {
      const { data } = nip19.decode(naddr);
      return data as { kind: number, pubkey: string, identifier: string };
    } catch (e) {
      console.error(`Failed to decode naddr: ${naddr}`, e);
      return null;
    }
  }
  return null;
}

// Fetch events by naddr identifiers
export async function fetchEventsByNaddrs(naddrs: string[]) {
  if (!naddrs || !Array.isArray(naddrs) || naddrs.length === 0) {
    console.warn('No valid naddrs provided to fetchEventsByNaddrs');
    return [];
  }

  try {
    await ndk.connect();

    const events = [];

    for (const naddr of naddrs) {
      try {
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
      } catch (error) {
        console.error(`Error processing naddr ${naddr}:`, error);
      }
    }

    return events;
  } catch (error) {
    console.error('Error in fetchEventsByNaddrs:', error);
    return [];
  }
}

// Fetch profile metadata for a pubkey with caching and timeout
export async function fetchProfileMetadata(pubkey: string) {
  // Check cache first
  const cached = profileCache[pubkey] as CachedProfile;
  if (cached && (Date.now() - cached.timestamp) < CACHE_EXPIRY) {
    return cached.data;
  }

  await ndk.connect();

  const filter = {
    kinds: [0],
    authors: [pubkey]
  };

  let profileEvents: any[] = [];
  try {
    const fetchPromise = ndk.fetchEvents(filter);
    const timeoutPromise = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('Profile fetch timeout')), 3000)
    );

    const events = await Promise.race([fetchPromise, timeoutPromise]) as any;
    profileEvents = Array.from(events);
  } catch (error) {
    console.error(`Error fetching profile for ${pubkey}:`, error);
    return null;
  }

  if (profileEvents.length === 0) {
    return null;
  }

  const profileEvent = profileEvents.sort((a: any, b: any) => {
    const aCreatedAt = a.created_at || 0;
    const bCreatedAt = b.created_at || 0;
    return bCreatedAt - aCreatedAt;
  })[0];

  try {
    const profileData = JSON.parse(profileEvent.content);

    // Cache the result
    profileCache[pubkey] = {
      data: profileData,
      timestamp: Date.now()
    };

    return profileData;
  } catch (e) {
    console.error('Failed to parse profile metadata:', e);
    return null;
  }
}

// Fetch Legacy DVMs (kind 31990 with kinds 5000-7000)
export async function fetchLegacyDVMs() {
  try {
    await ndk.connect();

    const filter: NDKFilter = {
      kinds: [31990], // NIP-89 DVM announcements
    };

    const events = await ndk.fetchEvents(filter);
    const eventArray = Array.from(events);

    // Filter for DVMs that support kinds 5000-7000
    const legacyDVMs = eventArray.filter((event: any) => {
      const kindTags = event.tags.filter((t: string[]) => t[0] === 'k');
      return kindTags.some((tag: string[]) => {
        const kind = parseInt(tag[1]);
        return kind >= 5000 && kind <= 7000;
      });
    });

    return legacyDVMs;
  } catch (error) {
    console.error('Error fetching legacy DVMs:', error);
    return [];
  }
}

// Fetch ContextVM DVMs (kind 11316 - Server Announcement)
export async function fetchContextVMDVMs() {
  try {
    await ndk.connect();

    const filter: any = {
      kinds: [11316], // Server Announcement
    };

    const events = await ndk.fetchEvents(filter);
    return Array.from(events);
  } catch (error) {
    console.error('Error fetching ContextVM DVMs:', error);
    return [];
  }
}

// Fetch Encrypted DVMs (kind 11999)
export async function fetchEncryptedDVMs() {
  try {
    await ndk.connect();

    const filter: any = {
      kinds: [11999], // Encrypted DVM announcements
    };

    const events = await ndk.fetchEvents(filter);
    return Array.from(events);
  } catch (error) {
    console.error('Error fetching encrypted DVMs:', error);
    return [];
  }
}

// Parse DVM profile from kind 31990 event
export function parseLegacyDVMProfile(event: any) {
  try {
    const content = JSON.parse(event.content);

    // Extract supported kinds from 'k' tags
    const kindTags = event.tags.filter((t: string[]) => t[0] === 'k');
    const supportedKinds = kindTags.map((tag: string[]) => parseInt(tag[1]));

    // Extract d tag (identifier)
    const dTag = event.tags.find((t: string[]) => t[0] === 'd')?.[1] || '';

    return {
      pubkey: event.pubkey,
      name: content.name || 'Unknown DVM',
      about: content.about || '',
      picture: content.picture || content.image || '',
      supportedKinds,
      identifier: dTag,
      createdAt: event.created_at,
      rawEvent: event
    };
  } catch (error) {
    console.error('Error parsing legacy DVM profile:', error);
    return null;
  }
}

// Parse ContextVM profile from kind 11316 event
export function parseContextVMProfile(event: any) {
  try {
    const content = JSON.parse(event.content);

    // Extract d tag (identifier)
    const dTag = event.tags.find((t: string[]) => t[0] === 'd')?.[1] || '';

    return {
      pubkey: event.pubkey,
      name: content.name || 'Unknown ContextVM',
      about: content.about || content.description || '',
      picture: content.picture || content.image || '',
      serverUrl: content.url || '',
      identifier: dTag,
      createdAt: event.created_at,
      rawEvent: event
    };
  } catch (error) {
    console.error('Error parsing ContextVM profile:', error);
    return null;
  }
}

// Parse Encrypted DVM profile from kind 11999 event
export function parseEncryptedDVMProfile(event: any) {
  try {
    const content = JSON.parse(event.content);

    // Extract d tag (identifier)
    const dTag = event.tags.find((t: string[]) => t[0] === 'd')?.[1] || '';

    // Extract supported kinds if present
    const kindTags = event.tags.filter((t: string[]) => t[0] === 'k');
    const supportedKinds = kindTags.map((tag: string[]) => parseInt(tag[1]));

    return {
      pubkey: event.pubkey,
      name: content.name || 'Unknown Encrypted DVM',
      about: content.about || content.description || '',
      picture: content.picture || content.image || '',
      supportedKinds,
      identifier: dTag,
      createdAt: event.created_at,
      rawEvent: event
    };
  } catch (error) {
    console.error('Error parsing encrypted DVM profile:', error);
    return null;
  }
}

// Generate naddr for an event
export function generateNaddr(kind: number, pubkey: string, dTag: string): string {
  try {
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

// Convert Nostr event to Article format (for /learn page)
export async function eventToArticle(event: any) {
  const titleTag = event.tags.find((t: string[]) => t[0] === 'title');
  const title = titleTag ? titleTag[1] : event.content.split('\n')[0].substring(0, 60);

  const authorPubkey = event.pubkey;

  let author = authorPubkey.substring(0, 8) + '...';
  try {
    const profileData = await fetchProfileMetadata(authorPubkey);
    if (profileData && profileData.name) {
      author = profileData.name;
    }
  } catch (error) {
    console.error('Error fetching profile metadata:', error);
  }

  const description = event.content.substring(0, 150) + (event.content.length > 150 ? '...' : '');

  const imageTag = event.tags.find((t: string[]) => t[0] === 'image');
  const imageUrl = imageTag ? imageTag[1] : undefined;

  const dTag = event.tags.find((t: string[]) => t[0] === 'd')?.[1] || '';
  const naddr = generateNaddr(event.kind, event.pubkey, dTag);

  const categoryTag = event.tags.find((t: string[]) => t[0] === 'c' || t[0] === 'category');
  let category = 'misc';

  if (categoryTag) {
    const tagValue = categoryTag[1].toLowerCase();
    if (tagValue.includes('tutorial') || tagValue.includes('guide') || tagValue.includes('how-to')) {
      category = 'tutorial';
    } else if (tagValue.includes('news') || tagValue.includes('update') || tagValue.includes('announcement')) {
      category = 'news';
    }
  }

  const wordCount = event.content.split(/\s+/).length;
  const readTime = Math.max(1, Math.ceil(wordCount / 200)) + ' min';

  return {
    title,
    author,
    url: `https://habla.news/a/${naddr}`,
    primalUrl: `https://primal.net/a/${naddr}`,
    description,
    category,
    readTime,
    imageUrl,
    naddr,
    createdAt: event.created_at,
    nostrEvent: event
  };
}

// Re-initialize NDK with new relays (note: requires page reload to take effect)
export function reinitializeNDK(relays: string[]) {
  console.log('Relay settings updated. Please reload the page for changes to take effect.');
  localStorage.setItem('dvmdash-relays', JSON.stringify(relays));
  return ndk;
}
