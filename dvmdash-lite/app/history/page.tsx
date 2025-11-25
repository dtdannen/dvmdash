'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { nip19 } from 'nostr-tools'
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

interface HistoricalData {
  metadata: {
    generated_at: string
    description: string
  }
  totals: {
    total_dvms: number
    total_users: number
    total_kinds: number
    total_requests: number
    total_responses: number
    monitoring_start: string
    monitoring_end: string
  }
  monthly_activity: Array<{
    month: string
    requests: number
    responses: number
    unique_dvms: number
    unique_kinds: number
    unique_users: number
    cumulative_requests: number
    cumulative_responses: number
  }>
  dvm_growth: Array<{
    month: string
    new_dvms: number
    cumulative_dvms: number
  }>
  user_growth: Array<{
    month: string
    new_users: number
    cumulative_users: number
  }>
  top_dvms: Array<{
    id: string
    name: string | null
    nip05: string | null
    first_seen: string
    last_seen: string
    total_responses: number
    total_feedback: number
  }>
  top_kinds: Array<{
    kind: number
    dvm_count: number
    total_requests: number
    total_responses: number
  }>
  relay_data: {
    total_unique_relays: number
    top_relays: Array<{
      relay_url: string
      usage_count: number
      unique_users: number
    }>
    relay_growth: Array<{
      month: string
      new_relays: number
      cumulative_relays: number
    }>
    relay_by_entity_type: {
      dvm_relays: number
      user_relays: number
      shared_relays: number
    }
  }
  ecosystem_health: {
    monthly_health: Array<{
      year_month: string
      total_requests: number
      total_responses: number
      response_rate: number
    }>
  }
  milestones: Array<{
    date: string
    event: string
    description: string
  }>
}

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short' })
}

function hexToNpub(hex: string): string {
  try {
    return nip19.npubEncode(hex)
  } catch {
    return hex
  }
}

function formatMilestoneDate(dateString: string): string {
  // Check if it's just a month (YYYY-MM-01 pattern from peak activity)
  if (dateString.endsWith('-01') && dateString.length === 10) {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long' })
  }
  // Full date
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
}

function StatCard({ label, value, subtext }: { label: string; value: string | number; subtext?: string }) {
  return (
    <div className="bg-card border rounded-xl p-6 text-center">
      <p className="text-muted-foreground text-sm mb-2">{label}</p>
      <p className="text-4xl font-bold text-primary">{typeof value === 'number' ? formatNumber(value) : value}</p>
      {subtext && <p className="text-xs text-muted-foreground mt-2">{subtext}</p>}
    </div>
  )
}

export default function HistoryPage() {
  const [data, setData] = useState<HistoricalData | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'overview' | 'dvms' | 'activity' | 'relays'>('overview')

  useEffect(() => {
    fetch('/dvmdash_historical.json')
      .then((res) => res.json())
      .then((json) => {
        setData(json)
        setLoading(false)
      })
      .catch((err) => {
        console.error('Failed to load historical data:', err)
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading historical data...</p>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Failed to load historical data</p>
      </div>
    )
  }

  const monitoringStart = formatDate(data.totals.monitoring_start)
  const monitoringEnd = formatDate(data.totals.monitoring_end)

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-8 max-w-7xl">
        {/* Header */}
        <header className="mb-8">
          <Link href="/" className="text-muted-foreground hover:text-primary mb-4 inline-flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Home
          </Link>
          <h1 className="text-4xl md:text-5xl font-bold mb-4">DVM Ecosystem History</h1>
          <p className="text-xl text-muted-foreground">
            Chronicling {monitoringStart} - {monitoringEnd}
          </p>
          <p className="text-muted-foreground mt-2">{data.metadata.description}</p>
        </header>

        {/* Hero Stats */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-12">
          <StatCard label="Total DVMs" value={data.totals.total_dvms} />
          <StatCard label="Total Users" value={data.totals.total_users} />
          <StatCard label="Total Events" value={data.totals.total_requests + data.totals.total_responses} />
          <StatCard label="DVM Types" value={data.totals.total_kinds} />
          <StatCard label="Relays Used" value={data.relay_data.total_unique_relays} subtext="by DVMs & users" />
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-2 mb-8 border-b overflow-x-auto">
          {(['overview', 'dvms', 'activity', 'relays'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 font-medium capitalize whitespace-nowrap transition-colors ${
                activeTab === tab
                  ? 'text-primary border-b-2 border-primary'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === 'overview' && (
          <div className="space-y-12">
            {/* Ecosystem Growth */}
            <section>
              <h2 className="text-2xl font-bold mb-6">Ecosystem Growth</h2>
              <div className="bg-card border rounded-xl p-6">
                <h3 className="text-lg font-semibold mb-4">Cumulative DVMs & Users Over Time</h3>
                <ResponsiveContainer width="100%" height={400}>
                  <AreaChart data={data.dvm_growth.map((d, i) => ({
                    ...d,
                    cumulative_users: data.user_growth[i]?.cumulative_users || 0
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="month" stroke="#888" fontSize={12} />
                    <YAxis yAxisId="left" stroke="#888" fontSize={12} />
                    <YAxis yAxisId="right" orientation="right" stroke="#888" fontSize={12} tickFormatter={formatNumber} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333' }}
                      labelStyle={{ color: '#fff' }}
                      formatter={(value: number, name: string) => [formatNumber(value), name]}
                    />
                    <Legend />
                    <Area
                      yAxisId="left"
                      type="monotone"
                      dataKey="cumulative_dvms"
                      name="Total DVMs"
                      stroke="#8b5cf6"
                      fill="#8b5cf6"
                      fillOpacity={0.3}
                    />
                    <Area
                      yAxisId="right"
                      type="monotone"
                      dataKey="cumulative_users"
                      name="Total Users"
                      stroke="#ec4899"
                      fill="#ec4899"
                      fillOpacity={0.3}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>

            {/* Monthly Activity */}
            <section>
              <h2 className="text-2xl font-bold mb-6">Monthly Activity</h2>
              <div className="bg-card border rounded-xl p-6">
                <h3 className="text-lg font-semibold mb-4">Events Per Month</h3>
                <ResponsiveContainer width="100%" height={400}>
                  <BarChart data={data.monthly_activity.map(m => ({
                    ...m,
                    events: m.requests + m.responses
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="month" stroke="#888" fontSize={12} />
                    <YAxis stroke="#888" fontSize={12} tickFormatter={formatNumber} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333' }}
                      labelStyle={{ color: '#fff' }}
                      formatter={(value: number) => formatNumber(value)}
                    />
                    <Bar dataKey="events" name="Events" fill="#8b5cf6" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>

            {/* Milestones */}
            <section>
              <h2 className="text-2xl font-bold mb-6">Key Milestones</h2>
              <div className="bg-card border rounded-xl p-6">
                <div className="space-y-4">
                  {data.milestones.map((milestone, i) => (
                    <div key={i} className="flex items-start gap-4 pb-4 border-b last:border-0">
                      <div className="bg-primary/20 text-primary px-3 py-1 rounded text-sm font-mono">
                        {formatMilestoneDate(milestone.date.slice(0, 10))}
                      </div>
                      <div>
                        <p className="font-medium">{milestone.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          </div>
        )}

        {activeTab === 'dvms' && (
          <div className="space-y-12">
            {/* DVM Growth Chart */}
            <section>
              <h2 className="text-2xl font-bold mb-6">DVM Growth Over Time</h2>
              <div className="bg-card border rounded-xl p-6">
                <ResponsiveContainer width="100%" height={400}>
                  <LineChart data={data.dvm_growth}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="month" stroke="#888" fontSize={12} />
                    <YAxis stroke="#888" fontSize={12} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333' }}
                      labelStyle={{ color: '#fff' }}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="cumulative_dvms"
                      name="Total DVMs"
                      stroke="#8b5cf6"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="new_dvms"
                      name="New DVMs"
                      stroke="#f59e0b"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>

            {/* Top DVMs */}
            <section>
              <h2 className="text-2xl font-bold mb-6">Top DVMs by Activity</h2>
              <div className="bg-card border rounded-xl overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-muted/50">
                      <tr>
                        <th className="text-left px-4 py-3 font-medium">#</th>
                        <th className="text-left px-4 py-3 font-medium">DVM</th>
                        <th className="text-right px-4 py-3 font-medium">Responses</th>
                        <th className="text-right px-4 py-3 font-medium">First Seen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.top_dvms.slice(0, 20).map((dvm, i) => (
                        <tr key={dvm.id} className="border-t hover:bg-muted/30">
                          <td className="px-4 py-3 text-muted-foreground">{i + 1}</td>
                          <td className="px-4 py-3">
                            <p className="font-medium">{dvm.name || 'Unknown'}</p>
                            <p className="text-xs text-muted-foreground font-mono break-all">{hexToNpub(dvm.id)}</p>
                          </td>
                          <td className="px-4 py-3 text-right font-mono">{formatNumber(dvm.total_responses)}</td>
                          <td className="px-4 py-3 text-right text-muted-foreground">
                            {formatDate(dvm.first_seen)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>

            {/* Top Kinds */}
            <section>
              <h2 className="text-2xl font-bold mb-6">Most Popular DVM Types (Kinds)</h2>
              <div className="bg-card border rounded-xl p-6">
                <ResponsiveContainer width="100%" height={400}>
                  <BarChart data={data.top_kinds.slice(0, 15)} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis type="number" stroke="#888" fontSize={12} tickFormatter={formatNumber} />
                    <YAxis type="category" dataKey="kind" stroke="#888" fontSize={12} width={60} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333' }}
                      labelStyle={{ color: '#fff' }}
                      formatter={(value: number) => formatNumber(value)}
                    />
                    <Legend />
                    <Bar dataKey="total_requests" name="Requests" fill="#3b82f6" />
                    <Bar dataKey="dvm_count" name="DVMs Supporting" fill="#8b5cf6" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>
        )}

        {activeTab === 'activity' && (
          <div className="space-y-12">
            {/* Cumulative Activity */}
            <section>
              <h2 className="text-2xl font-bold mb-6">Cumulative Events</h2>
              <div className="bg-card border rounded-xl p-6">
                <p className="text-muted-foreground mb-4">
                  Total DVM-related events (requests + responses) observed over time.
                </p>
                <ResponsiveContainer width="100%" height={400}>
                  <AreaChart data={data.monthly_activity.map(m => ({
                    ...m,
                    cumulative_events: m.cumulative_requests + m.cumulative_responses
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="month" stroke="#888" fontSize={12} />
                    <YAxis stroke="#888" fontSize={12} tickFormatter={formatNumber} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333' }}
                      labelStyle={{ color: '#fff' }}
                      formatter={(value: number) => formatNumber(value)}
                    />
                    <Area
                      type="monotone"
                      dataKey="cumulative_events"
                      name="Total Events"
                      stroke="#8b5cf6"
                      fill="#8b5cf6"
                      fillOpacity={0.3}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>

            {/* User Growth */}
            <section>
              <h2 className="text-2xl font-bold mb-6">User Growth</h2>
              <div className="bg-card border rounded-xl p-6">
                <ResponsiveContainer width="100%" height={400}>
                  <AreaChart data={data.user_growth}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="month" stroke="#888" fontSize={12} />
                    <YAxis stroke="#888" fontSize={12} tickFormatter={formatNumber} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333' }}
                      labelStyle={{ color: '#fff' }}
                      formatter={(value: number) => formatNumber(value)}
                    />
                    <Legend />
                    <Area
                      type="monotone"
                      dataKey="cumulative_users"
                      name="Total Users"
                      stroke="#ec4899"
                      fill="#ec4899"
                      fillOpacity={0.3}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>
        )}

        {activeTab === 'relays' && (
          <div className="space-y-12">
            {/* Relay Stats */}
            <section>
              <h2 className="text-2xl font-bold mb-6">Relay Usage in DVM Events</h2>
              <p className="text-muted-foreground mb-6">
                DVMs and users specify which relays to use for communication in their event tags.
                This shows the relay preferences across the ecosystem.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                <StatCard
                  label="Total Unique Relays"
                  value={data.relay_data.total_unique_relays}
                  subtext="Specified in events"
                />
                <StatCard
                  label="DVM-Used Relays"
                  value={data.relay_data.relay_by_entity_type.dvm_relays}
                  subtext="Relays DVMs advertised"
                />
                <StatCard
                  label="User-Used Relays"
                  value={data.relay_data.relay_by_entity_type.user_relays}
                  subtext="Relays users specified"
                />
              </div>
            </section>

            {/* Relay Growth */}
            <section>
              <h2 className="text-2xl font-bold mb-6">New Relays Seen Over Time</h2>
              <div className="bg-card border rounded-xl p-6">
                <ResponsiveContainer width="100%" height={400}>
                  <AreaChart data={data.relay_data.relay_growth}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="month" stroke="#888" fontSize={12} />
                    <YAxis stroke="#888" fontSize={12} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333' }}
                      labelStyle={{ color: '#fff' }}
                    />
                    <Legend />
                    <Area
                      type="monotone"
                      dataKey="cumulative_relays"
                      name="Total Relays"
                      stroke="#f59e0b"
                      fill="#f59e0b"
                      fillOpacity={0.3}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>

            {/* Top Relays */}
            <section>
              <h2 className="text-2xl font-bold mb-6">Most Popular Relays</h2>
              <div className="bg-card border rounded-xl overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-muted/50">
                      <tr>
                        <th className="text-left px-4 py-3 font-medium">#</th>
                        <th className="text-left px-4 py-3 font-medium">Relay</th>
                        <th className="text-right px-4 py-3 font-medium">Usage Count</th>
                        <th className="text-right px-4 py-3 font-medium">Unique Users</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.relay_data.top_relays.slice(0, 25).map((relay, i) => (
                        <tr key={relay.relay_url} className="border-t hover:bg-muted/30">
                          <td className="px-4 py-3 text-muted-foreground">{i + 1}</td>
                          <td className="px-4 py-3 font-mono text-sm">{relay.relay_url}</td>
                          <td className="px-4 py-3 text-right font-mono">{formatNumber(relay.usage_count)}</td>
                          <td className="px-4 py-3 text-right font-mono">{formatNumber(relay.unique_users)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          </div>
        )}

        {/* Footer */}
        <footer className="text-center text-muted-foreground text-sm mt-16 border-t pt-8">
          <p>Data generated on {new Date(data.metadata.generated_at).toLocaleDateString()}</p>
          <p className="mt-2">
            <Link href="/" className="text-primary hover:underline">
              Back to DVMDash Lite
            </Link>
          </p>
        </footer>
      </div>
    </div>
  )
}
