import type { Metadata, ResolvingMetadata } from 'next'
import { getApiUrl } from '@/lib/api'
import { createCompleteMetadata } from '@/lib/metadata-utils'

// Function to fetch global stats data for metadata
export async function fetchGlobalStats() {
  try {
    // For server-side metadata requests, use the metadata API URL if available
    const metadataApiUrl = process.env.NEXT_PUBLIC_METADATA_API_URL || process.env.NEXT_PUBLIC_API_URL;
    const apiUrl = typeof window === 'undefined' && metadataApiUrl ? metadataApiUrl : getApiUrl('');
    
    // Log environment information
    console.log('Environment in fetchGlobalStats:', {
      isServer: typeof window === 'undefined',
      NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
      NEXT_PUBLIC_METADATA_API_URL: process.env.NEXT_PUBLIC_METADATA_API_URL,
      metadataApiUrl,
      apiUrl,
      fullUrl: `${apiUrl}/api/stats/global/latest?timeRange=30d`
    });
    
    // Use the metadata API URL for server-side requests
    const res = await fetch(`${apiUrl}/api/stats/global/latest?timeRange=30d`, {
      next: { revalidate: 60 } // Revalidate every minute
    })
    
    if (!res.ok) {
      throw new Error(`Failed to fetch global stats: ${res.status}`)
    }
    
    return await res.json()
  } catch (error) {
    console.error('Error fetching global stats for metadata:', error)
    return null
  }
}

export async function generateDashboardMetadata(
  _: any,
  parent: ResolvingMetadata
): Promise<Metadata> {
  // Default values for metadata
  const title = 'DVMDash Stats'
  const defaultDescription = "Statistics for Data Vending Machines (DVMs) on Nostr provided by DVMDash"
  const imageUrl = 'https://dvmdashbucket.nyc3.cdn.digitaloceanspaces.com/DVMDash.png'
  const canonicalUrl = 'https://stats.dvmdash.live'
  
  // Try to fetch global stats, but don't let it block metadata generation
  let description = defaultDescription
  try {
    const globalStats = await fetchGlobalStats()
    
    // Create description with stats if available
    if (globalStats) {
      description = `DVMDash Stats: Tracking ${globalStats.unique_dvms.toLocaleString()} DVMs, ${globalStats.unique_kinds.toLocaleString()} kinds, and ${globalStats.total_requests.toLocaleString()} requests on Nostr`
    }
  } catch (error) {
    console.error('Failed to fetch global stats for metadata, using default description:', error)
  }
  
  // Get previous images from parent metadata
  const previousImages = (await parent).openGraph?.images || []
  
  return {
    metadataBase: new URL('https://stats.dvmdash.live'),
    title: {
      template: '%s | DVMDash Stats',
      default: title,
    },
    description,
    ...createCompleteMetadata(
      title,
      description,
      imageUrl,
      canonicalUrl,
      previousImages,
      'Dataset',
      500, // Image width
      500  // Image height
    )
  }
}
