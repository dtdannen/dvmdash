'use client'

import { useState, useMemo } from 'react'
import Link from 'next/link'
import { cn } from "@/lib/utils"
import { Card, CardContent } from "@/components/ui/card"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { BarChart3, Bot, Tags, Home, Search, LayoutGrid, List } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { useDVMList } from '@/lib/api'
import { TimeRangeSelector } from './time-range-selector'
import { TimeWindow, NavIconProps, DVMListItem } from '@/lib/types'

const NavIcon = ({ Icon, href, isActive, label }: NavIconProps) => (
  <Link
    href={href}
    className={cn(
      "inline-flex items-center justify-center w-12 h-12 rounded-lg transition-colors",
      "hover:bg-muted",
      isActive && "bg-primary text-primary-foreground hover:bg-primary"
    )}
    aria-label={label}
  >
    <Icon className="h-5 w-5" />
  </Link>
)

interface DVMCardProps {
  dvm: DVMListItem
}

const DVMCard = ({ dvm }: DVMCardProps) => {
  const displayName = dvm.dvm_name || dvm.id
  const initials = displayName.substring(0, 2).toUpperCase()
  const lastSeenDate = new Date(dvm.last_seen)
  const timeAgo = Math.round((Date.now() - lastSeenDate.getTime()) / (1000 * 60)) // minutes ago

  return (
    <Link href={`/dvm-stats/${dvm.id}`} className="block">
      <Card className="overflow-hidden cursor-pointer hover:bg-muted/50 transition-colors">
        <CardContent className="p-4">
          <div className="flex items-center space-x-4">
            <Avatar>
              {dvm.dvm_picture ? (
                <AvatarImage src={dvm.dvm_picture} alt={displayName} />
              ) : null}
              <AvatarFallback>{initials}</AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{displayName}</p>
              <p className="text-xs text-muted-foreground truncate">
                {dvm.supported_kinds.length} supported kinds • {dvm.num_supporting_kinds} supporting
              </p>
            </div>
          </div>
          <div className="mt-4 space-y-2 text-xs text-muted-foreground">
            <div className="flex justify-between">
              <span>Requests: {dvm.total_requests?.toLocaleString() ?? '0'}</span>
              <span>Responses: {dvm.total_responses?.toLocaleString() ?? '0'}</span>
            </div>
            <div className="flex justify-between">
              <span>Last seen: {timeAgo}m ago</span>
              <span>{dvm.is_active ? '🟢 Active' : '⚫️ Inactive'}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}

interface DVMTableProps {
  dvms: DVMListItem[]
}

type SortableColumn = 'id' | 'supported_kinds' | 'supported_kinds_first' | 'total_requests' | 'total_responses' | 'last_seen'

const DVMTable = ({ dvms }: DVMTableProps) => {
  const [sortColumn, setSortColumn] = useState<SortableColumn | null>(null)
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')

  const handleHeaderClick = (column: SortableColumn) => {
    if (sortColumn === column) {
      // Toggle direction if clicking the same column
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      // Set new column and default to ascending
      setSortColumn(column)
      setSortDirection('asc')
    }
  }

  const sortedDVMs = useMemo(() => {
    if (!sortColumn) return dvms

    return [...dvms].sort((a, b) => {
      let aValue, bValue

      // Special handling for id column which should sort by name if available
      if (sortColumn === 'id') {
        aValue = a.dvm_name || a.id
        bValue = b.dvm_name || b.id
        return sortDirection === 'asc' 
          ? String(aValue).localeCompare(String(bValue))
          : String(bValue).localeCompare(String(aValue))
      }
      
      // Handle array length for supported_kinds or first kind for supported_kinds_first
      if (sortColumn === 'supported_kinds') {
        aValue = a.supported_kinds.length
        bValue = b.supported_kinds.length
      } else if (sortColumn === 'supported_kinds_first') {
        // Sort by the first kind in the list, or 0 if the list is empty
        aValue = a.supported_kinds.length > 0 ? a.supported_kinds[0] : 0
        bValue = b.supported_kinds.length > 0 ? b.supported_kinds[0] : 0
      } else if (sortColumn === 'last_seen') {
        // Date comparison for last_seen
        aValue = new Date(a.last_seen).getTime()
        bValue = new Date(b.last_seen).getTime()
      } else {
        // For other numeric columns
        aValue = a[sortColumn] || 0
        bValue = b[sortColumn] || 0
      }

      // Sort based on direction
      return sortDirection === 'asc' ? aValue - bValue : bValue - aValue
    })
  }, [dvms, sortColumn, sortDirection])

  // Helper to render sort indicator
  const renderSortIndicator = (column: SortableColumn) => {
    if (sortColumn !== column) return null
    return <span className="ml-1">{sortDirection === 'asc' ? '↑' : '↓'}</span>
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead 
            className="cursor-pointer hover:bg-muted/50"
            onClick={() => handleHeaderClick('id')}
          >
            DVM {renderSortIndicator('id')}
          </TableHead>
          <TableHead 
            className="text-right cursor-pointer hover:bg-muted/50"
            onClick={() => handleHeaderClick('supported_kinds')}
          >
            Kinds {renderSortIndicator('supported_kinds')}
          </TableHead>
          <TableHead 
            className="cursor-pointer hover:bg-muted/50"
            onClick={() => handleHeaderClick('supported_kinds_first')}
          >
            Supported Kinds {renderSortIndicator('supported_kinds_first')}
          </TableHead>
          <TableHead 
            className="text-right cursor-pointer hover:bg-muted/50"
            onClick={() => handleHeaderClick('total_requests')}
          >
            Requests {renderSortIndicator('total_requests')}
          </TableHead>
          <TableHead 
            className="text-right cursor-pointer hover:bg-muted/50"
            onClick={() => handleHeaderClick('total_responses')}
          >
            Responses {renderSortIndicator('total_responses')}
          </TableHead>
          <TableHead 
            className="text-right cursor-pointer hover:bg-muted/50"
            onClick={() => handleHeaderClick('last_seen')}
          >
            Last Seen {renderSortIndicator('last_seen')}
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sortedDVMs.map((dvm: DVMListItem) => (
          <TableRow key={dvm.id} className="cursor-pointer hover:bg-muted/50 transition-colors">
            <TableCell className="font-medium">
              <Link href={`/dvm-stats/${dvm.id}`} className="hover:underline flex items-center">
                {dvm.dvm_picture && (
                  <Avatar className="h-6 w-6 mr-2">
                    <AvatarImage src={dvm.dvm_picture} alt={dvm.dvm_name || dvm.id} />
                    <AvatarFallback>{(dvm.dvm_name || dvm.id).substring(0, 2).toUpperCase()}</AvatarFallback>
                  </Avatar>
                )}
                {dvm.dvm_name || dvm.id}
              </Link>
            </TableCell>
            <TableCell className="text-right">{dvm.supported_kinds.length}</TableCell>
            <TableCell>
              <div className="flex flex-wrap gap-2">
                {dvm.supported_kinds.map((kind) => (
                  <Link 
                    key={kind} 
                    href={`/kind-stats/${kind}`}
                    className="inline-flex items-center px-2 py-1 rounded-md bg-muted hover:bg-muted/80 text-xs font-medium transition-colors"
                  >
                    {kind}
                  </Link>
                ))}
              </div>
            </TableCell>
            <TableCell className="text-right">{dvm.total_requests?.toLocaleString() ?? '0'}</TableCell>
            <TableCell className="text-right">{dvm.total_responses?.toLocaleString() ?? '0'}</TableCell>
            <TableCell className="text-right">{new Date(dvm.last_seen).toLocaleString()}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function DVMList() {
  const [searchTerm, setSearchTerm] = useState('')
  const [isCardView, setIsCardView] = useState(true)
  const [timeRange, setTimeRange] = useState<TimeWindow>('30d')
  const { dvmList, isLoading, isError } = useDVMList(100, 0, timeRange as TimeWindow)

  // Filter DVMs based on search term (match against ID or name)
  const filteredDVMs = dvmList?.dvms.filter((dvm: DVMListItem) => {
    const searchTermLower = searchTerm.toLowerCase();
    return dvm.id.toLowerCase().includes(searchTermLower) || 
           (dvm.dvm_name && dvm.dvm_name.toLowerCase().includes(searchTermLower));
  }) || []

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container flex h-16 items-center justify-between pl-2 pr-4">
          <div className="flex items-center space-x-3">
            <NavIcon
              Icon={Home}
              href="/"
              isActive={false}
              label="Return to Main Page"
            />
            <h1 className="text-xl font-bold">DVMs</h1>
          </div>
          <div className="flex-1 flex justify-center">
            <nav className="flex items-center space-x-2" aria-label="Main Navigation">
              <NavIcon
                Icon={BarChart3}
                href="/"
                isActive={false}
                label="Summary Stats"
              />
              <NavIcon
                Icon={Bot}
                href="/dvm-stats"
                isActive={true}
                label="Per DVM Stats"
              />
              <NavIcon
                Icon={Tags}
                href="/kind-stats"
                isActive={false}
                label="Per Kind Stats"
              />
            </nav>
          </div>
          <div className="flex items-center space-x-2">
            <TimeRangeSelector timeRange={timeRange} setTimeRange={setTimeRange} />
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="container mx-auto p-4">
        <div className="mb-6 flex justify-between items-center">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 transform text-muted-foreground" />
            <Input
              type="search"
              placeholder="Search DVMs..."
              className="pl-8"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <div className="flex items-center space-x-2">
            <Label htmlFor="view-toggle" className="sr-only">
              Toggle view
            </Label>
            <Switch
              id="view-toggle"
              checked={isCardView}
              onCheckedChange={setIsCardView}
            />
            <span className="text-sm text-muted-foreground">
              {isCardView ? <LayoutGrid className="h-4 w-4" /> : <List className="h-4 w-4" />}
            </span>
          </div>
        </div>

        {isLoading ? (
          <div className="text-center">Loading DVMs...</div>
        ) : isError ? (
          <div className="text-center text-red-500">Error loading DVMs</div>
        ) : (
          isCardView ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
              {filteredDVMs.map((dvm: DVMListItem) => (
                <DVMCard key={dvm.id} dvm={dvm} />
              ))}
            </div>
          ) : (
            <DVMTable dvms={filteredDVMs} />
          )
        )}
      </main>
    </div>
  )
}
