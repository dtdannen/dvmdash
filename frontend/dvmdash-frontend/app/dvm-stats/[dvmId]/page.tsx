'use client'

import { DVMStats } from '@/components/dvm-stats'
import { useParams } from 'next/navigation'

export default function DVMStatsPage() {
  const params = useParams()
  
  // Debug logging
  console.log("DVMStatsPage Render:", {
    params,
    dvmId: params.dvmId
  });

  if (!params.dvmId || typeof params.dvmId !== 'string') {
    console.error("Invalid DVM ID:", params);
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p>Invalid DVM ID</p>
      </div>
    )
  }

  // Keep the component simple like the kind stats page
  return <DVMStats dvmId={params.dvmId} />
}
