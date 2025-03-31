import { KindStats } from '@/components/kind-stats'
import type { Metadata, ResolvingMetadata } from 'next'
import { getApiUrl } from '@/lib/api'
import { createCompleteMetadata } from '@/lib/metadata-utils'

type Props = {
  params: { kind: string }
  searchParams: { [key: string]: string | string[] | undefined }
}

// Function to fetch Kind data for metadata
async function fetchKindData(kindId: number) {
  try {
    // For server-side metadata requests, use the metadata API URL if available
    const metadataApiUrl = process.env.NEXT_PUBLIC_METADATA_API_URL || process.env.NEXT_PUBLIC_API_URL;
    const apiUrl = typeof window === 'undefined' && metadataApiUrl ? metadataApiUrl : getApiUrl('');
    
    // Log environment information
    console.log('Environment in fetchKindData:', {
      kindId,
      isServer: typeof window === 'undefined',
      NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
      NEXT_PUBLIC_METADATA_API_URL: process.env.NEXT_PUBLIC_METADATA_API_URL,
      metadataApiUrl,
      apiUrl,
      fullUrl: `${apiUrl}/api/stats/kind/${kindId}?timeRange=30d`
    });
    
    // Use the metadata API URL for server-side requests
    const res = await fetch(`${apiUrl}/api/stats/kind/${kindId}?timeRange=30d`, {
      next: { revalidate: 60 } // Revalidate every minute
    })
    
    if (!res.ok) {
      throw new Error(`Failed to fetch Kind data: ${res.status}`)
    }
    
    return await res.json()
  } catch (error) {
    console.error('Error fetching Kind data for metadata:', error)
    return null
  }
}

export async function generateMetadata(
  { params }: Props,
  parent: ResolvingMetadata
): Promise<Metadata> {
  // Parse kind to number and validate
  const kindId = parseInt(params.kind, 10)
  if (isNaN(kindId)) {
    return {
      title: 'Invalid Kind ID | DVMDash Stats',
      description: 'The requested Kind ID is invalid',
    }
  }
  
  // Get the canonical URL
  const canonicalUrl = `https://stats.dvmdash.live/kind-stats/${kindId}`
  
  // Default values for metadata
  const title = `Kind ${kindId}`
  let description = `Statistics for Nostr Kind ${kindId}`
  const imageUrl = 'https://dvmdashbucket.nyc3.cdn.digitaloceanspaces.com/DVMDash.png'
  
  // Try to fetch Kind data, but don't let it block metadata generation
  try {
    const kindData = await fetchKindData(kindId)
    
    if (kindData) {
      // Update description if data fetch succeeds
      description = `Statistics for Nostr Kind ${kindId} with ${kindData.num_supporting_dvms} supporting DVMs`
    }
  } catch (error) {
    console.error(`Failed to fetch Kind data for metadata (${kindId}), using default values:`, error)
  }
  
  // Get previous images from parent metadata
  const previousImages = (await parent).openGraph?.images || []
  
  // Use the utility function to create complete metadata
  return createCompleteMetadata(
    title,
    description,
    imageUrl,
    canonicalUrl,
    previousImages,
    'Dataset', // Schema.org type
    500, // Image width
    500  // Image height
  )
}

export default function KindStatsPage({ params }: Props) {
  // Parse kind to number and validate
  const kindId = parseInt(params.kind, 10)
  if (isNaN(kindId)) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p>Invalid kind ID</p>
      </div>
    )
  }

  return <KindStats kindId={kindId} />
}
