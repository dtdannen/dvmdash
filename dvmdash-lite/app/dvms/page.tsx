'use client'

import { useEffect, useState } from 'react'
import { Input } from '@/components/ui/input'
import { Search } from 'lucide-react'
import { DVMFilters, DVMType } from '@/components/dvm-filters'
import { ViewToggle, ViewMode } from '@/components/view-toggle'
import { RelaySettings } from '@/components/relay-settings'
import { DVMProfileCard } from '@/components/dvm-profile-card'
import { DVMListView } from '@/components/dvm-list-view'
import { LoadingSpinner } from '@/components/loading-spinner'
import {
  fetchLegacyDVMs,
  fetchContextVMDVMs,
  fetchEncryptedDVMs,
  parseLegacyDVMProfile,
  parseContextVMProfile,
  parseEncryptedDVMProfile,
  reinitializeNDK
} from '@/lib/nostr'

interface DVMProfile {
  pubkey: string
  name: string
  about: string
  picture: string
  supportedKinds?: number[]
  serverUrl?: string
  identifier: string
  createdAt: number
  type: 'legacy' | 'context' | 'encrypted'
}

export default function DVMsPage() {
  const [allProfiles, setAllProfiles] = useState<DVMProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedType, setSelectedType] = useState<DVMType>('all')
  const [viewMode, setViewMode] = useState<ViewMode>('grid')

  // Load view preference from localStorage
  useEffect(() => {
    const savedView = localStorage.getItem('dvmdash-view-mode')
    if (savedView === 'list' || savedView === 'grid') {
      setViewMode(savedView)
    }
  }, [])

  // Save view preference to localStorage
  useEffect(() => {
    localStorage.setItem('dvmdash-view-mode', viewMode)
  }, [viewMode])

  // Fetch all DVMs on mount
  useEffect(() => {
    async function loadDVMs() {
      setLoading(true)
      console.log('Starting to load DVMs...')
      try {
        const [legacyEvents, contextEvents, encryptedEvents] = await Promise.all([
          fetchLegacyDVMs(),
          fetchContextVMDVMs(),
          fetchEncryptedDVMs()
        ])

        console.log('All fetch promises resolved', {
          legacyCount: legacyEvents.length,
          contextCount: contextEvents.length,
          encryptedCount: encryptedEvents.length
        })

        const legacyProfiles: DVMProfile[] = legacyEvents
          .map((event) => {
            const parsed = parseLegacyDVMProfile(event)
            return parsed ? { ...parsed, type: 'legacy' as const } : null
          })
          .filter(Boolean) as DVMProfile[]

        const contextProfiles: DVMProfile[] = contextEvents
          .map((event) => {
            const parsed = parseContextVMProfile(event)
            return parsed ? { ...parsed, type: 'context' as const } : null
          })
          .filter(Boolean) as DVMProfile[]

        const encryptedProfiles: DVMProfile[] = encryptedEvents
          .map((event) => {
            const parsed = parseEncryptedDVMProfile(event)
            return parsed ? { ...parsed, type: 'encrypted' as const } : null
          })
          .filter(Boolean) as DVMProfile[]

        const combined = [...legacyProfiles, ...contextProfiles, ...encryptedProfiles]
        // Sort by most recent first
        combined.sort((a, b) => b.createdAt - a.createdAt)

        console.log(`Total ${combined.length} DVMs loaded`)
        setAllProfiles(combined)
      } catch (error) {
        console.error('Error loading DVMs:', error)
      } finally {
        console.log('Loading complete')
        setLoading(false)
      }
    }

    loadDVMs()
  }, [])

  // Handle relay changes
  const handleRelaysChange = (relays: string[]) => {
    reinitializeNDK(relays)
    // Optionally reload DVMs with new relays
    // You could add a refresh button or auto-reload here
  }

  // Filter profiles
  const filteredProfiles = allProfiles.filter((profile) => {
    // Type filter
    if (selectedType !== 'all' && profile.type !== selectedType) {
      return false
    }

    // Search filter
    if (searchTerm) {
      const searchLower = searchTerm.toLowerCase()
      return (
        profile.name.toLowerCase().includes(searchLower) ||
        profile.about.toLowerCase().includes(searchLower) ||
        profile.pubkey.toLowerCase().includes(searchLower) ||
        (profile.serverUrl && profile.serverUrl.toLowerCase().includes(searchLower))
      )
    }

    return true
  })

  // Calculate counts
  const counts = {
    all: allProfiles.length,
    legacy: allProfiles.filter(p => p.type === 'legacy').length,
    encrypted: allProfiles.filter(p => p.type === 'encrypted').length,
    context: allProfiles.filter(p => p.type === 'context').length,
  }

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 py-8 max-w-7xl">
        {/* Header */}
        <header className="mb-8">
          <h1 className="text-4xl font-bold mb-3">
            Data Vending Machines
          </h1>
          <p className="text-muted-foreground">
            Explore all DVMs across the Nostr network - legacy, encrypted, and context-aware services
          </p>
        </header>

        {/* Search Bar */}
        <div className="mb-6">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search DVMs by name, description, pubkey, or server URL..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>

        {/* Filters */}
        <div className="mb-6">
          <DVMFilters
            selectedType={selectedType}
            onTypeChange={setSelectedType}
            counts={counts}
          />
        </div>

        {/* Relay Settings */}
        <RelaySettings onRelaysChange={handleRelaysChange} />

        {/* View Toggle and Count */}
        <div className="flex items-center justify-between mb-6">
          <div className="text-sm text-muted-foreground">
            Showing {filteredProfiles.length} {filteredProfiles.length === 1 ? 'DVM' : 'DVMs'}
          </div>
          <ViewToggle view={viewMode} onViewChange={setViewMode} />
        </div>

        {/* Loading State */}
        {loading && (
          <div className="flex justify-center items-center py-16">
            <LoadingSpinner />
          </div>
        )}

        {/* DVMs Display */}
        {!loading && filteredProfiles.length > 0 && (
          <>
            {viewMode === 'grid' ? (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredProfiles.map((profile) => (
                  <DVMProfileCard key={profile.pubkey} profile={profile} type={profile.type} />
                ))}
              </div>
            ) : (
              <DVMListView profiles={filteredProfiles} />
            )}
          </>
        )}

        {/* Empty State */}
        {!loading && filteredProfiles.length === 0 && (
          <div className="text-center py-16">
            <div className="text-6xl mb-4">🤖</div>
            <h3 className="text-xl font-semibold mb-2">No DVMs found</h3>
            <p className="text-muted-foreground">
              {searchTerm
                ? 'Try adjusting your search terms or filters'
                : 'No DVMs are currently available'}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
