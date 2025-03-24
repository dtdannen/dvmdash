import { DVMStats } from '@/components/dvm-stats'
import type { Metadata, ResolvingMetadata } from 'next'
import { API_BASE } from '@/lib/api'

type Props = {
  params: { dvmId: string }
  searchParams: { [key: string]: string | string[] | undefined }
}

// Function to fetch DVM data for metadata
async function fetchDVMData(dvmId: string) {
  try {
    const res = await fetch(`${API_BASE}/api/stats/dvm/${dvmId}?timeRange=30d`, {
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
  
  // Fetch DVM data
  const dvmData = await fetchDVMData(dvmId)
  
  // Get the canonical URL
  const canonicalUrl = `https://stats.dvmdash.live/dvm-stats/${dvmId}`
  
  // Get previous images from parent metadata
  const previousImages = (await parent).openGraph?.images || []
  
  // Default values if data fetch fails
  const title = dvmData?.dvm_name || `DVM ${dvmId.slice(0, 8)}...`
  const description = dvmData?.dvm_about || 
    `Statistics for Data Vending Machine (DVM) ${dvmId.slice(0, 8)}... on Nostr`
  
  // Use DVM picture if available, otherwise use a default image
  const imageUrl = dvmData?.dvm_picture || 'https://stats.dvmdash.live/api/og-image'
  
  return {
    title,
    description,
    openGraph: {
      type: 'website',
      url: canonicalUrl,
      title,
      description,
      images: [
        {
          url: imageUrl,
          width: 1200,
          height: 630,
          alt: `${title} stats visualization`,
        },
        ...previousImages,
      ],
      siteName: 'DVMDash Stats',
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [imageUrl],
    },
    alternates: {
      canonical: canonicalUrl,
    },
  }
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
