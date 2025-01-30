'use client'

import { useState } from 'react'
import Link from 'next/link'
import { cn } from "@/lib/utils"
import { Card, CardContent } from "@/components/ui/card"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useRouter } from 'next/navigation'
import { BarChart3, Bot, Tags, Home, Search, LayoutGrid, List } from 'lucide-react'
import { useDVMList } from '@/lib/api'
import { TimeRangeSelector } from './time-range-selector'
import { TimeWindow, NavIconProps, DVMListItem } from '@/lib/types'
import { LucideIcon } from 'lucide-react'

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
  const router = useRouter()
  const initials = dvm.id.substring(0, 2).toUpperCase()
  const lastSeenDate = new Date(dvm.last_seen)
  const timeAgo = Math.round((Date.now() - lastSeenDate.getTime()) / (1000 * 60)) // minutes ago

  return (
    <Card className="overflow-hidden cursor-pointer" onClick={() => router.push(`/dvm-stats/${dvm.id}`)}>
      <CardContent className="p-4">
        <div className="flex items-center space-x-4">
          <Avatar>
            <AvatarFallback>{initials}</AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate">{dvm.id}</p>
            <p className="text-xs text-gray-500 truncate">
              {dvm.supported_kinds.length} supported kinds
            </p>
          </div>
        </div>
        <div className="mt-4 flex justify-between text-xs text-gray-500">
          <span>{dvm.total_events?.toLocaleString() ?? '0'} events</span>
          <span>{timeAgo}m ago</span>
        </div>
      </CardContent>
    </Card>
  )
}

interface DVMTableProps {
  dvms: DVMListItem[]
}

const DVMTable = ({ dvms }: DVMTableProps) => {
  const router = useRouter()
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>ID</TableHead>
          <TableHead>Supported Kinds</TableHead>
          <TableHead>Total Events</TableHead>
          <TableHead>Last Seen</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {dvms.map((dvm: DVMListItem) => (
          <TableRow key={dvm.id} className="cursor-pointer" onClick={() => router.push(`/dvm-stats/${dvm.id}`)}>
            <TableCell className="font-medium">{dvm.id}</TableCell>
            <TableCell>{dvm.supported_kinds.length}</TableCell>
            <TableCell>{dvm.total_events?.toLocaleString() ?? '0'}</TableCell>
            <TableCell>{new Date(dvm.last_seen).toLocaleString()}</TableCell>
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

  // Filter DVMs based on search term
  const filteredDVMs = dvmList?.dvms.filter((dvm: DVMListItem) =>
    dvm.id.toLowerCase().includes(searchTerm.toLowerCase())
  ) || []

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
          <div className="flex items-center">
            <TimeRangeSelector timeRange={timeRange} setTimeRange={setTimeRange} />
          </div>
        </div>
      </header>

      <main className="container mx-auto p-4">
        <div className="mb-6 flex justify-between items-center">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 transform text-gray-500" />
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
            <span className="text-sm text-gray-500">
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
