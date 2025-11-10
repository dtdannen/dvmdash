'use client'

import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from './ui/dialog'
import { Button } from './ui/button'
import { Copy, ExternalLink } from 'lucide-react'

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

interface DVMDetailDialogProps {
  profile: DVMProfile
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function DVMDetailDialog({ profile, open, onOpenChange }: DVMDetailDialogProps) {
  const [imageError, setImageError] = useState(false)
  const [copiedPubkey, setCopiedPubkey] = useState(false)

  const copyPubkey = () => {
    navigator.clipboard.writeText(profile.pubkey)
    setCopiedPubkey(true)
    setTimeout(() => setCopiedPubkey(false), 2000)
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
        return 'Legacy DVM'
      case 'context':
        return 'ContextVM Server'
      case 'encrypted':
        return 'Encrypted DVM'
    }
  }

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <div className="flex items-start gap-4 mb-4">
            {/* Avatar */}
            <div className="flex-shrink-0">
              {profile.picture && !imageError ? (
                <img
                  src={profile.picture}
                  alt={profile.name}
                  className="w-20 h-20 rounded-full object-cover"
                  onError={() => setImageError(true)}
                />
              ) : (
                <div className="w-20 h-20 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white text-3xl font-bold">
                  {profile.name.charAt(0).toUpperCase()}
                </div>
              )}
            </div>

            {/* Title and Type */}
            <div className="flex-1 min-w-0">
              <DialogTitle className="text-2xl mb-2">{profile.name}</DialogTitle>
              <span className={`px-3 py-1 rounded text-sm border ${getTypeBadgeClass(profile.type)}`}>
                {getTypeLabel(profile.type)}
              </span>
            </div>
          </div>

          {profile.about && (
            <DialogDescription className="text-base mt-4">
              {profile.about}
            </DialogDescription>
          )}
        </DialogHeader>

        <div className="space-y-6 mt-6">
          {/* Public Key */}
          <div>
            <h3 className="text-sm font-semibold text-muted-foreground mb-2">Public Key</h3>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-sm bg-muted px-3 py-2 rounded font-mono break-all">
                {profile.pubkey}
              </code>
              <Button
                variant="outline"
                size="icon"
                onClick={copyPubkey}
                title={copiedPubkey ? 'Copied!' : 'Copy pubkey'}
              >
                <Copy className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Server URL (for ContextVM) */}
          {profile.serverUrl && (
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-2">Server URL</h3>
              <a
                href={profile.serverUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-primary hover:underline flex items-center gap-2 break-all"
              >
                {profile.serverUrl}
                <ExternalLink className="h-4 w-4 flex-shrink-0" />
              </a>
            </div>
          )}

          {/* Supported Kinds */}
          {profile.supportedKinds && profile.supportedKinds.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-2">
                Supported Kinds ({profile.supportedKinds.length})
              </h3>
              <div className="flex flex-wrap gap-2 max-h-64 overflow-y-auto bg-muted/30 p-3 rounded">
                {profile.supportedKinds.sort((a, b) => a - b).map((kind) => (
                  <span
                    key={kind}
                    className={`px-2 py-1 rounded text-xs font-mono ${getTypeBadgeClass(profile.type)}`}
                  >
                    {kind}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="grid grid-cols-2 gap-4 pt-4 border-t">
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-1">Identifier</h3>
              <p className="text-sm font-mono">{profile.identifier || 'N/A'}</p>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-1">Created</h3>
              <p className="text-sm">{formatDate(profile.createdAt)}</p>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
