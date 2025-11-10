'use client'

import { useState } from 'react'
import { Copy, ExternalLink } from 'lucide-react'
import { Button } from './ui/button'

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

interface DVMListViewProps {
  profiles: DVMProfile[]
}

export function DVMListView({ profiles }: DVMListViewProps) {
  const [copiedPubkey, setCopiedPubkey] = useState<string | null>(null)

  const copyPubkey = (pubkey: string) => {
    navigator.clipboard.writeText(pubkey)
    setCopiedPubkey(pubkey)
    setTimeout(() => setCopiedPubkey(null), 2000)
  }

  const getTypeBadgeClass = (type: 'legacy' | 'context' | 'encrypted') => {
    switch (type) {
      case 'legacy':
        return 'bg-purple-500/20 text-purple-300 border-purple-500/50'
      case 'context':
        return 'bg-green-500/20 text-green-300 border-green-500/50'
      case 'encrypted':
        return 'bg-pink-500/20 text-pink-300 border-pink-500/50'
    }
  }

  const getTypeLabel = (type: 'legacy' | 'context' | 'encrypted') => {
    switch (type) {
      case 'legacy':
        return 'Legacy'
      case 'context':
        return 'ContextVM'
      case 'encrypted':
        return 'Encrypted'
    }
  }

  return (
    <div className="space-y-2">
      {profiles.map((profile) => (
        <div
          key={profile.pubkey}
          className="flex items-center gap-4 p-4 border rounded-lg hover:bg-muted/50 transition-colors"
        >
          {/* Avatar */}
          <div className="flex-shrink-0">
            {profile.picture ? (
              <img
                src={profile.picture}
                alt={profile.name}
                className="w-12 h-12 rounded-full object-cover"
                onError={(e) => {
                  e.currentTarget.style.display = 'none'
                  e.currentTarget.nextElementSibling?.classList.remove('hidden')
                }}
              />
            ) : null}
            <div className={`w-12 h-12 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white font-bold ${profile.picture ? 'hidden' : ''}`}>
              {profile.name.charAt(0).toUpperCase()}
            </div>
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-semibold truncate">{profile.name}</h3>
              <span className={`px-2 py-0.5 rounded text-xs border ${getTypeBadgeClass(profile.type)}`}>
                {getTypeLabel(profile.type)}
              </span>
            </div>
            <p className="text-sm text-muted-foreground truncate">{profile.about || 'No description'}</p>
          </div>

          {/* Metadata */}
          <div className="hidden md:flex items-center gap-4 text-sm text-muted-foreground">
            {profile.supportedKinds && profile.supportedKinds.length > 0 && (
              <div className="text-center">
                <div className="font-semibold text-foreground">{profile.supportedKinds.length}</div>
                <div className="text-xs">Kinds</div>
              </div>
            )}
            {profile.serverUrl && (
              <a
                href={profile.serverUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline flex items-center gap-1"
              >
                Server
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>

          {/* Actions */}
          <div className="flex-shrink-0">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => copyPubkey(profile.pubkey)}
              title={copiedPubkey === profile.pubkey ? 'Copied!' : 'Copy pubkey'}
            >
              <Copy className="h-4 w-4" />
            </Button>
          </div>
        </div>
      ))}
    </div>
  )
}
