'use client'

import { DVMStats } from '@/components/dvm-stats'
import { useParams } from 'next/navigation'

export default function DVMStatsPage() {
  const params = useParams()
  console.log("URL Params:", params); // Debug log
  return <DVMStats dvmId={params.dvmId as string} />
}