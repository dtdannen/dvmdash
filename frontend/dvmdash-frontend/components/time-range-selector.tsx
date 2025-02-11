'use client'

import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { TimeWindow, TimeRangeSelectorProps } from '@/lib/types'

export function TimeRangeSelector({ timeRange, setTimeRange }: TimeRangeSelectorProps) {
  return (
    <Tabs value={timeRange} onValueChange={(value) => setTimeRange(value as TimeWindow)} className="w-full max-w-xs">
      <TabsList className="grid w-full grid-cols-4 h-9">
        <TabsTrigger value="1h" className="text-xs">1h</TabsTrigger>
        <TabsTrigger value="24h" className="text-xs">24h</TabsTrigger>
        <TabsTrigger value="7d" className="text-xs">7d</TabsTrigger>
        <TabsTrigger value="30d" className="text-xs">30d</TabsTrigger>
      </TabsList>
    </Tabs>
  )
}
