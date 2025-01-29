'use client'

import { KindStats } from '@/components/kind-stats'
import { useParams } from 'next/navigation'

export default function KindStatsPage() {
  const params = useParams()
  const kind = params.kind
  
  // Parse kind to number and validate
  const kindId = parseInt(kind as string, 10)
  if (isNaN(kindId)) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p>Invalid kind ID</p>
      </div>
    )
  }

  return <KindStats kindId={kindId} />
}
