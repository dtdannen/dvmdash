import { DVMList } from '@/components/dvm-list'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'DVM List',
  description: 'List of all Data Vending Machines (DVMs) tracked by DVMDash',
  openGraph: {
    title: 'DVM List | DVMDash Stats',
    description: 'List of all Data Vending Machines (DVMs) tracked by DVMDash',
  },
  twitter: {
    title: 'DVM List | DVMDash Stats',
    description: 'List of all Data Vending Machines (DVMs) tracked by DVMDash',
  }
}

export default function DVMStatsIndexPage() {
  return <DVMList />
}
