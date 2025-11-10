'use client'

import { useState, useEffect } from 'react'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card'
import { X, Plus, ChevronDown, ChevronUp } from 'lucide-react'

const DEFAULT_RELAYS = [
  'wss://relay.damus.io',
  'wss://relay.primal.net',
  'wss://relay.nostr.band',
  'wss://nos.lol'
]

interface RelaySettingsProps {
  onRelaysChange?: (relays: string[]) => void
}

export function RelaySettings({ onRelaysChange }: RelaySettingsProps) {
  const [relays, setRelays] = useState<string[]>(DEFAULT_RELAYS)
  const [newRelay, setNewRelay] = useState('')
  const [isExpanded, setIsExpanded] = useState(false)
  const [isInitialized, setIsInitialized] = useState(false)

  // Load relays from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('dvmdash-relays')
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        setRelays(parsed)
      } catch (e) {
        console.error('Failed to parse saved relays:', e)
      }
    }
    setIsInitialized(true)
  }, [])

  // Save relays to localStorage and notify parent (skip on initial mount)
  useEffect(() => {
    if (!isInitialized) return

    localStorage.setItem('dvmdash-relays', JSON.stringify(relays))
    if (onRelaysChange) {
      onRelaysChange(relays)
    }
  }, [relays, onRelaysChange, isInitialized])

  const addRelay = () => {
    const trimmed = newRelay.trim()
    if (trimmed && trimmed.startsWith('wss://') && !relays.includes(trimmed)) {
      setRelays([...relays, trimmed])
      setNewRelay('')
    }
  }

  const removeRelay = (relay: string) => {
    if (relays.length > 1) {
      setRelays(relays.filter(r => r !== relay))
    }
  }

  const resetToDefaults = () => {
    setRelays(DEFAULT_RELAYS)
  }

  return (
    <Card className="mb-6">
      <CardHeader className="pb-3">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center justify-between w-full text-left"
        >
          <CardTitle className="text-base">Relay Settings</CardTitle>
          {isExpanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </button>
      </CardHeader>
      
      {isExpanded && (
        <CardContent className="space-y-3">
          <div className="space-y-2">
            {relays.map((relay) => (
              <div key={relay} className="flex items-center gap-2">
                <Input
                  value={relay}
                  readOnly
                  className="flex-1 text-sm"
                />
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => removeRelay(relay)}
                  disabled={relays.length === 1}
                  title="Remove relay"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>

          <div className="flex gap-2">
            <Input
              placeholder="wss://relay.example.com"
              value={newRelay}
              onChange={(e) => setNewRelay(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addRelay()}
              className="flex-1 text-sm"
            />
            <Button
              onClick={addRelay}
              size="icon"
              title="Add relay"
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={resetToDefaults}
            className="w-full"
          >
            Reset to Defaults
          </Button>

          <p className="text-xs text-muted-foreground">
            {relays.length} relay{relays.length !== 1 ? 's' : ''} configured
          </p>
        </CardContent>
      )}
    </Card>
  )
}
