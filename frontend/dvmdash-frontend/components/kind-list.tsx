import { useState } from 'react'
import Link from 'next/link'
import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { BarChart3, Bot, Tags, Home, Search } from 'lucide-react'
import { useKindList } from '@/lib/api'

const NavIcon = ({ Icon, href, isActive, label }) => (
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

const KindTable = ({ kinds }) => {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Kind</TableHead>
          <TableHead className="text-right">Requests</TableHead>
          <TableHead className="text-right">Responses</TableHead>
          <TableHead className="text-right">Supporting DVMs</TableHead>
          <TableHead className="text-right">Last Seen</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {kinds.map((kind) => (
          <TableRow key={kind.kind}>
            <TableCell className="font-medium">{kind.kind}</TableCell>
            <TableCell className="text-right">{kind.num_requests.toLocaleString()}</TableCell>
            <TableCell className="text-right">{kind.num_responses.toLocaleString()}</TableCell>
            <TableCell className="text-right">{kind.num_supporting_dvms}</TableCell>
            <TableCell className="text-right">{new Date(kind.last_seen).toLocaleString()}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function KindList() {
  const [searchTerm, setSearchTerm] = useState('')
  const { kindList, isLoading, isError } = useKindList(100, 0) // Updated hook name

  // Filter kinds based on search term
  const filteredKinds = kindList?.kinds.filter(kind =>
    kind.kind.toString().includes(searchTerm)
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
            <h1 className="text-xl font-bold">Kinds</h1>
          </div>
          <div className="flex-1 flex justify-center">
            <nav className="flex items-center space-x-2" aria-label="Main Navigation">
              <NavIcon
                Icon={BarChart3}
                href="/stats"
                isActive={false}
                label="Summary Stats"
              />
              <NavIcon
                Icon={Bot}
                href="/dvm-stats"
                isActive={false}
                label="Per DVM Stats"
              />
              <NavIcon
                Icon={Tags}
                href="/kind-stats"
                isActive={true}
                label="Per Kind Stats"
              />
            </nav>
          </div>
        </div>
      </header>

      <main className="container mx-auto p-4">
        <div className="mb-6 flex justify-between items-center">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 transform text-gray-500" />
            <Input
              type="search"
              placeholder="Search kinds..."
              className="pl-8"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
        </div>

        {isLoading ? (
          <div className="text-center">Loading kinds...</div>
        ) : isError ? (
          <div className="text-center text-red-500">Error loading kinds</div>
        ) : (
          <KindTable kinds={filteredKinds} />
        )}
      </main>
    </div>
  )
}