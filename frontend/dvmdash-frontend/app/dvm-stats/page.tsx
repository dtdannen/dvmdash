import { DVMList } from '@/components/dvm-list'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'DVM List',
  description: 'List of all Data Vending Machines (DVMs) tracked by DVMDash',
  openGraph: {
    title: 'DVM List | DVMDash Stats',
    description: 'List of all Data Vending Machines (DVMs) tracked by DVMDash',
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
    title: 'DVM List | DVMDash Stats',
    description: 'List of all Data Vending Machines (DVMs) tracked by DVMDash',
    images: ['https://dvmdashbucket.nyc3.cdn.digitaloceanspaces.com/DVMDash.png'],
  }
}

export default function DVMStatsIndexPage() {
  return <DVMList />
}
