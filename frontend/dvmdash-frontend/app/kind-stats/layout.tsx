import type { Metadata } from 'next'
import { createOpenGraphMetadata, createTwitterMetadata } from '@/lib/metadata-utils'

// Constants for metadata
const title = 'Kind List'
const fullTitle = 'Kind List | DVMDash Stats'
const description = 'List of all Nostr Kinds tracked by DVMDash'
const imageUrl = 'https://dvmdashbucket.nyc3.cdn.digitaloceanspaces.com/DVMDash.png'
const canonicalUrl = 'https://stats.dvmdash.live/kind-stats'

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

export default function KindStatsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
