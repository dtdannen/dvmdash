import { KindStats } from '@/components/kind-stats'
import type { Metadata, ResolvingMetadata } from 'next'
import { API_BASE } from '@/lib/api'

type Props = {
  params: { kind: string }
  searchParams: { [key: string]: string | string[] | undefined }
}

// Function to fetch Kind data for metadata
async function fetchKindData(kindId: number) {
  try {
    const res = await fetch(`${API_BASE}/api/stats/kind/${kindId}?timeRange=30d`, {
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
  
  // Fetch Kind data
  const kindData = await fetchKindData(kindId)
  
  // Get the canonical URL
  const canonicalUrl = `https://stats.dvmdash.live/kind-stats/${kindId}`
  
  // Get previous images from parent metadata
  const previousImages = (await parent).openGraph?.images || []
  
  // Default values if data fetch fails
  const title = `Kind ${kindId}`
  const description = kindData 
    ? `Statistics for Nostr Kind ${kindId} with ${kindData.num_supporting_dvms} supporting DVMs`
    : `Statistics for Nostr Kind ${kindId}`
  
  // Use a default image for kind stats
  const imageUrl = 'https://stats.dvmdash.live/api/og-image'
  
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
