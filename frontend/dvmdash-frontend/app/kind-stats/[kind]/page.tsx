'use client'

import { KindStats } from '@/components/kind-stats'
import { useParams } from 'next/navigation'

export default function KindStatsPage() {
  const params = useParams()
  console.log("URL Params:", params); // Debug log
  return <KindStats kindId={params.kindId as string} />
}