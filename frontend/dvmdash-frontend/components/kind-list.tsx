'use client'

import { useState, useMemo, useEffect } from 'react'
import Link from 'next/link'
import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { BarChart3, Bot, Tags, Home, Search, ExternalLink } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { useKindList } from '@/lib/api'
import { NavIconProps, KindListResponse, TimeWindow, KindListItem } from '@/lib/types'
import { fetchWikiForKind, extractTitle, generateWikiUrl } from '@/lib/nostr-wiki'
import { Button } from "@/components/ui/button"
import { TimeRangeSelector } from './time-range-selector'

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

// Extend KindListItem to include wiki information
interface KindWithWiki extends KindListItem {
  wikiTitle?: string;
  wikiUrl?: string;
  isLoadingWiki?: boolean;
}

interface KindTableProps {
  kinds: KindListResponse['kinds']
}

type SortableColumn = 'kind' | 'total_requests' | 'total_responses' | 'num_supporting_dvms' | 'last_seen'

const KindTable = ({ kinds }: KindTableProps) => {
  const [sortColumn, setSortColumn] = useState<SortableColumn | null>(null)
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')
  const [wikiData, setWikiData] = useState<Record<number, { title?: string, url?: string, isLoading: boolean }>>({})
  
  // Initialize wiki data for each kind - only once when component mounts
  useEffect(() => {
    // Create a map to track which kinds we've already fetched wiki data for
    const fetchedKinds = new Set<number>();
    
    // Function to update wiki data for a specific kind
    const fetchWikiForKindIfNeeded = async (kind: KindListItem) => {
      // Skip if we've already fetched this kind
      if (fetchedKinds.has(kind.kind)) return;
      
      // Mark this kind as fetched
      fetchedKinds.add(kind.kind);
      
      // Set loading state
      setWikiData(prev => ({
        ...prev,
        [kind.kind]: { isLoading: true }
      }));
      
      try {
        const wikiEvent = await fetchWikiForKind(kind.kind);
        if (wikiEvent) {
          setWikiData(prev => ({
            ...prev,
            [kind.kind]: {
              title: extractTitle(wikiEvent),
              url: generateWikiUrl(wikiEvent),
              isLoading: false
            }
          }));
        } else {
          setWikiData(prev => ({
            ...prev,
            [kind.kind]: {
              isLoading: false
            }
          }));
        }
      } catch (error) {
        console.error(`Error fetching wiki for kind ${kind.kind}:`, error);
        setWikiData(prev => ({
          ...prev,
          [kind.kind]: {
            isLoading: false
          }
        }));
      }
    };
    
    // Fetch wiki data for each kind
    kinds.forEach(kind => fetchWikiForKindIfNeeded(kind));
    
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty dependency array means this only runs once when component mounts
  
  // Update wiki data for new kinds that appear in the list
  useEffect(() => {
    // Only process kinds that don't have wiki data yet
    kinds.forEach(kind => {
      if (!wikiData[kind.kind]) {
        setWikiData(prev => ({
          ...prev,
          [kind.kind]: { isLoading: true }
        }));
        
        fetchWikiForKind(kind.kind)
          .then(wikiEvent => {
            if (wikiEvent) {
              setWikiData(prev => ({
                ...prev,
                [kind.kind]: {
                  title: extractTitle(wikiEvent),
                  url: generateWikiUrl(wikiEvent),
                  isLoading: false
                }
              }));
            } else {
              setWikiData(prev => ({
                ...prev,
                [kind.kind]: {
                  isLoading: false
                }
              }));
            }
          })
          .catch(error => {
            console.error(`Error fetching wiki for kind ${kind.kind}:`, error);
            setWikiData(prev => ({
              ...prev,
              [kind.kind]: {
                isLoading: false
              }
            }));
          });
      }
    });
  }, [kinds, wikiData]);

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

  const sortedKinds = useMemo(() => {
    if (!sortColumn) return kinds

    return [...kinds].sort((a, b) => {
      let aValue, bValue

      if (sortColumn === 'last_seen') {
        // Date comparison for last_seen
        aValue = new Date(a.last_seen).getTime()
        bValue = new Date(b.last_seen).getTime()
      } else {
        // For numeric columns
        aValue = a[sortColumn] || 0
        bValue = b[sortColumn] || 0
      }

      // Sort based on direction
      return sortDirection === 'asc' ? aValue - bValue : bValue - aValue
    })
  }, [kinds, sortColumn, sortDirection])

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
            onClick={() => handleHeaderClick('kind')}
          >
            Kind {renderSortIndicator('kind')}
          </TableHead>
          <TableHead>
            Description
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
            onClick={() => handleHeaderClick('num_supporting_dvms')}
          >
            Supporting DVMs {renderSortIndicator('num_supporting_dvms')}
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
        {sortedKinds.map((kind) => (
          <TableRow key={kind.kind}>
            <TableCell className="font-medium">
              <Link href={`/kind-stats/${kind.kind}`} className="hover:underline">
                {kind.kind}
              </Link>
            </TableCell>
            <TableCell>
              {wikiData[kind.kind]?.isLoading ? (
                <span className="text-muted-foreground text-sm">Loading wiki...</span>
              ) : wikiData[kind.kind]?.title ? (
                <div className="flex items-center">
                  <span>{wikiData[kind.kind].title}</span>
                  {wikiData[kind.kind].url && (
                    <Button variant="ghost" size="sm" className="ml-2 p-0 h-8 w-8" asChild>
                      <a href={wikiData[kind.kind].url} target="_blank" rel="noopener noreferrer" title="View Wiki">
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    </Button>
                  )}
                </div>
              ) : (
                <span className="text-muted-foreground text-sm">No description available</span>
              )}
            </TableCell>
            <TableCell className="text-right">{kind.total_requests?.toLocaleString() ?? '0'}</TableCell>
            <TableCell className="text-right">{kind.total_responses?.toLocaleString() ?? '0'}</TableCell>
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
  const [timeRange, setTimeRange] = useState<TimeWindow>('30d')
  const { kindList, isLoading, isError } = useKindList(100, 0, timeRange)

  // Filter kinds based on search term
  const filteredKinds = kindList?.kinds.filter((kind: KindListItem) =>
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
                href="/"
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
