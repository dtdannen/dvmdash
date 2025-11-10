'use client'

import { useState } from 'react'
import { Card, CardContent, CardHeader } from './ui/card'
import { Button } from './ui/button'
import { Copy } from 'lucide-react'
import { cn } from '@/lib/utils'
import { DVMDetailDialog } from './dvm-detail-dialog'

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

interface DVMProfileCardProps {
  profile: DVMProfile
  type: 'legacy' | 'context' | 'encrypted'
}

export function DVMProfileCard({ profile, type }: DVMProfileCardProps) {
  const [imageError, setImageError] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)

  const truncatePubkey = (pubkey: string) => {
    return `${pubkey.substring(0, 8)}...${pubkey.substring(pubkey.length - 8)}`
  }

  const typeColors = {
    legacy: 'border-purple-500/50',
    context: 'border-green-500/50',
    encrypted: 'border-pink-500/50',
  }

  const badgeColors = {
    legacy: 'bg-purple-500/20 text-purple-300',
    context: 'bg-green-500/20 text-green-300',
    encrypted: 'bg-pink-500/20 text-pink-300',
  }

  return (
    <>
      <Card
        className={cn('hover:bg-muted/50 transition-all duration-300 cursor-pointer', typeColors[type])}
        onClick={() => setDialogOpen(true)}
      >
        <CardHeader className="pb-3">
          <div className="flex items-start gap-4">
          {/* Avatar */}
          <div className="flex-shrink-0">
            {profile.picture && !imageError ? (
              <img
                src={profile.picture}
                alt={profile.name}
                className="w-16 h-16 rounded-full object-cover"
                onError={() => setImageError(true)}
              />
            ) : (
              <div className="w-16 h-16 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white text-2xl font-bold">
                {profile.name.charAt(0).toUpperCase()}
              </div>
            )}
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <h3 className="text-xl font-semibold mb-1">{profile.name}</h3>
            <p className="text-sm text-muted-foreground font-mono">{truncatePubkey(profile.pubkey)}</p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {profile.about && (
          <p className="text-sm text-muted-foreground line-clamp-3">{profile.about}</p>
        )}

        {/* Supported Kinds */}
        {profile.supportedKinds && profile.supportedKinds.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-2">Supported Kinds:</p>
            <div className="flex flex-wrap gap-1">
              {profile.supportedKinds.slice(0, 5).map((kind) => (
                <span
                  key={kind}
                  className={`px-2 py-1 rounded text-xs font-mono ${badgeColors[type]}`}
                >
                  {kind}
                </span>
              ))}
              {profile.supportedKinds.length > 5 && (
                <span className="px-2 py-1 rounded text-xs text-muted-foreground">
                  +{profile.supportedKinds.length - 5} more
                </span>
              )}
            </div>
          </div>
        )}

        {/* Server URL (for ContextVM) */}
        {profile.serverUrl && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">Server:</p>
            <a
              href={profile.serverUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-primary hover:underline break-all"
            >
              {profile.serverUrl}
            </a>
          </div>
        )}

        {/* Copy Pubkey Button */}
        <Button
          variant="ghost"
          size="sm"
          onClick={(e) => {
            e.stopPropagation() // Prevent opening dialog
            navigator.clipboard.writeText(profile.pubkey)
          }}
          className="w-full"
        >
          <Copy className="w-4 h-4 mr-2" />
          Copy Pubkey
        </Button>
      </CardContent>
    </Card>

    {/* Detail Dialog */}
    <DVMDetailDialog
      profile={{ ...profile, type }}
      open={dialogOpen}
      onOpenChange={setDialogOpen}
    />
  </>
  )
}
