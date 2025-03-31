import { DVMStats } from '@/components/dvm-stats'
import type { Metadata, ResolvingMetadata } from 'next'
import { getApiUrl } from '@/lib/api'
import { createCompleteMetadata } from '@/lib/metadata-utils'

type Props = {
  params: { dvmId: string }
  searchParams: { [key: string]: string | string[] | undefined }
}

// Function to fetch DVM data for metadata
async function fetchDVMData(dvmId: string) {
  try {
    // For server-side metadata requests, use the metadata API URL if available
    const metadataApiUrl = process.env.NEXT_PUBLIC_METADATA_API_URL || process.env.NEXT_PUBLIC_API_URL;
    const apiUrl = typeof window === 'undefined' && metadataApiUrl ? metadataApiUrl : getApiUrl('');
    
    // Log environment information
    console.log('Environment in fetchDVMData:', {
      dvmId,
      isServer: typeof window === 'undefined',
      NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
      NEXT_PUBLIC_METADATA_API_URL: process.env.NEXT_PUBLIC_METADATA_API_URL,
      metadataApiUrl,
      apiUrl,
      fullUrl: `${apiUrl}/api/stats/dvm/${dvmId}?timeRange=30d`
    });
    
    // Use the metadata API URL for server-side requests
    const res = await fetch(`${apiUrl}/api/stats/dvm/${dvmId}?timeRange=30d`, {
      next: { revalidate: 60 } // Revalidate every minute
    })
    
    if (!res.ok) {
      throw new Error(`Failed to fetch DVM data: ${res.status}`)
    }
    
    return await res.json()
  } catch (error) {
    console.error('Error fetching DVM data for metadata:', error)
    return null
  }
}

export async function generateMetadata(
  { params }: Props,
  parent: ResolvingMetadata
): Promise<Metadata> {
  // Get DVM ID from params
  const dvmId = params.dvmId
  
  // Get the canonical URL
  const canonicalUrl = `https://stats.dvmdash.live/dvm-stats/${dvmId}`
  
  // Default values for metadata
  let title = `DVM ${dvmId.slice(0, 8)}...`
  let description = `Statistics for Data Vending Machine (DVM) ${dvmId.slice(0, 8)}... on Nostr`
  let imageUrl = 'https://dvmdashbucket.nyc3.cdn.digitaloceanspaces.com/DVMDash.png'
  let imageWidth = 500
  let imageHeight = 500
  
  // Try to fetch DVM data, but don't let it block metadata generation
  try {
    const dvmData = await fetchDVMData(dvmId)
    
    if (dvmData) {
      // Update values if data fetch succeeds
      title = dvmData.dvm_name || title
      description = dvmData.dvm_about || description
      
      // Use DVM picture if available
      if (dvmData.dvm_picture) {
        imageUrl = dvmData.dvm_picture
        imageWidth = 1200
        imageHeight = 630
      }
    }
  } catch (error) {
    console.error(`Failed to fetch DVM data for metadata (${dvmId}), using default values:`, error)
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
    imageWidth,
    imageHeight
  )
}

export default function DVMStatsPage({ params }: Props) {
  const dvmId = params.dvmId
  
  if (!dvmId) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p>Invalid DVM ID</p>
      </div>
    )
  }

  return <DVMStats dvmId={dvmId} />
}
