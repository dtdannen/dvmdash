import { KindList } from '@/components/kind-list'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Kind List',
  description: 'List of all Nostr Kinds tracked by DVMDash',
  openGraph: {
    title: 'Kind List | DVMDash Stats',
    description: 'List of all Nostr Kinds tracked by DVMDash',
    images: [
      {
        url: 'https://dvmdashbucket.nyc3.cdn.digitaloceanspaces.com/DVMDash.png',
        width: 500,
        height: 500,
        alt: 'DVMDash Stats',
      }
    ],
  },
  twitter: {
    title: 'Kind List | DVMDash Stats',
    description: 'List of all Nostr Kinds tracked by DVMDash',
    images: ['https://dvmdashbucket.nyc3.cdn.digitaloceanspaces.com/DVMDash.png'],
  }
}

export default function KindStatsIndexPage() {
  return <KindList />
}
