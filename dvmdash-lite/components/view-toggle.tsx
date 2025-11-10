'use client'

import { LayoutGrid, List } from 'lucide-react'
import { Button } from './ui/button'
import { cn } from '@/lib/utils'

export type ViewMode = 'grid' | 'list'

interface ViewToggleProps {
  view: ViewMode
  onViewChange: (view: ViewMode) => void
}

export function ViewToggle({ view, onViewChange }: ViewToggleProps) {
  return (
    <div className="flex items-center gap-1 border rounded-lg p-1">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onViewChange('grid')}
        className={cn(
          'h-8 px-3',
          view === 'grid' && 'bg-background shadow-sm'
        )}
      >
        <LayoutGrid className="h-4 w-4 mr-2" />
        Grid
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onViewChange('list')}
        className={cn(
          'h-8 px-3',
          view === 'list' && 'bg-background shadow-sm'
        )}
      >
        <List className="h-4 w-4 mr-2" />
        List
      </Button>
    </div>
  )
}
