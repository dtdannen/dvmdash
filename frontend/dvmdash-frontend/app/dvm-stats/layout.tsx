import type { Metadata } from 'next'
import { createOpenGraphMetadata, createTwitterMetadata } from '@/lib/metadata-utils'

// Constants for metadata
const title = 'DVM List'
const fullTitle = 'DVM List | DVMDash Stats'
const description = 'List of all Data Vending Machines (DVMs) tracked by DVMDash'
const imageUrl = 'https://dvmdashbucket.nyc3.cdn.digitaloceanspaces.com/DVMDash.png'
const canonicalUrl = 'https://stats.dvmdash.live/dvm-stats'

export const metadata: Metadata = {
  title,
  description,
  openGraph: createOpenGraphMetadata(
    fullTitle,
    description,
    imageUrl,
    canonicalUrl,
    500, // Image width
    500  // Image height
  ),
  twitter: createTwitterMetadata(
    fullTitle,
    description,
    imageUrl
  ),
  alternates: {
    canonical: canonicalUrl,
  }
}

export default function DVMStatsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
