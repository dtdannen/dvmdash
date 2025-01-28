// app/dvm-stats/page.tsx
'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function DVMStatsIndexPage() {
  const router = useRouter()

  useEffect(() => {
    // Either redirect to a specific DVM
    router.push('/dvm-stats/default-dvm-id')
    // Or show a list of DVMs to choose from
  }, [router])

  return <div>Loading...</div>
}