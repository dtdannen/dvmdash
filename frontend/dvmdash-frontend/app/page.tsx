'use client'

import { Dashboard } from "@/components/dashboard"
import type { Metadata, ResolvingMetadata } from 'next'
import { API_BASE } from '@/lib/api'

// Function to fetch global stats data for metadata
async function fetchGlobalStats() {
  try {
    const res = await fetch(`${API_BASE}/api/stats/global/latest?timeRange=30d`, {
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

export async function generateMetadata(
  _: any,
  parent: ResolvingMetadata
): Promise<Metadata> {
  // Fetch global stats
  const globalStats = await fetchGlobalStats()
  
  // Get previous images from parent metadata
  const previousImages = (await parent).openGraph?.images || []
  
  // Create description with stats if available
  let description = "Statistics for Data Vending Machines (DVMs) on Nostr provided by DVMDash"
  if (globalStats) {
    description = `DVMDash Stats: Tracking ${globalStats.unique_dvms.toLocaleString()} DVMs, ${globalStats.unique_kinds.toLocaleString()} kinds, and ${globalStats.total_requests.toLocaleString()} requests on Nostr`
  }
  
  // Use a default image for the dashboard
  const imageUrl = 'https://dvmdashbucket.nyc3.cdn.digitaloceanspaces.com/DVMDash.png'
  
  return {
    description,
    openGraph: {
      images: [
        {
          url: imageUrl,
          width: 500,
          height: 500,
          alt: 'DVMDash Stats visualization',
        },
        ...previousImages,
      ],
      description,
    },
    twitter: {
      images: [imageUrl],
      description,
    },
  }
}

export default function Page() {
  return <Dashboard />
}
