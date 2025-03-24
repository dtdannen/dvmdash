import { KindList } from '@/components/kind-list'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Kind List',
  description: 'List of all Nostr Kinds tracked by DVMDash',
  openGraph: {
    title: 'Kind List | DVMDash Stats',
    description: 'List of all Nostr Kinds tracked by DVMDash',
  },
  twitter: {
    title: 'Kind List | DVMDash Stats',
    description: 'List of all Nostr Kinds tracked by DVMDash',
  }
}

export default function KindStatsIndexPage() {
  return <KindList />
}
