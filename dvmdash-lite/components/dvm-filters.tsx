'use client'

import { Tabs, TabsList, TabsTrigger } from './ui/tabs'

export type DVMType = 'all' | 'legacy' | 'encrypted' | 'context'

interface DVMFiltersProps {
  selectedType: DVMType
  onTypeChange: (type: DVMType) => void
  counts: {
    all: number
    legacy: number
    encrypted: number
    context: number
  }
}

export function DVMFilters({ selectedType, onTypeChange, counts }: DVMFiltersProps) {
  return (
    <Tabs value={selectedType} onValueChange={(value) => onTypeChange(value as DVMType)}>
      <TabsList className="grid w-full grid-cols-4">
        <TabsTrigger value="all" className="text-xs sm:text-sm">
          All ({counts.all})
        </TabsTrigger>
        <TabsTrigger value="legacy" className="text-xs sm:text-sm">
          Legacy ({counts.legacy})
        </TabsTrigger>
        <TabsTrigger value="encrypted" className="text-xs sm:text-sm">
          Encrypted ({counts.encrypted})
        </TabsTrigger>
        <TabsTrigger value="context" className="text-xs sm:text-sm">
          ContextVM ({counts.context})
        </TabsTrigger>
      </TabsList>
    </Tabs>
  )
}
