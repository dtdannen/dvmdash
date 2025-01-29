'use client'

import { useState } from 'react'
import Link from 'next/link'
import { cn } from "@/lib/utils"
import { useKindStats, KindStats as KindStatsType } from '@/lib/api'
import type { TimeWindow, TimeRangeSelectorProps, ChartProps, NavIconProps } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { ArrowLeft, BarChart3, Bot, Tags, Settings, FileText, ArrowDownToLine, Users, Server, Hash, Star, Zap, Target, Brain, Home, Clock } from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

const TimeRangeSelector = ({ timeRange, setTimeRange }: TimeRangeSelectorProps) => (
  <Tabs value={timeRange} onValueChange={setTimeRange} className="w-full max-w-xs">
    <TabsList className="grid w-full grid-cols-5 h-9">
      <TabsTrigger value="1h" className="text-xs">1h</TabsTrigger>
      <TabsTrigger value="24h" className="text-xs">24h</TabsTrigger>
      <TabsTrigger value="7d" className="text-xs">7d</TabsTrigger>
      <TabsTrigger value="30d" className="text-xs">30d</TabsTrigger>
    </TabsList>
  </Tabs>
)

const RequestChart = ({ data }: ChartProps) => (
  <ResponsiveContainer width="100%" height={400}>
    <LineChart data={data}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="time" />
      <YAxis />
      <Tooltip />
      <Line type="monotone" dataKey="requests" stroke="#8884d8" name="Requests" />
    </LineChart>
  </ResponsiveContainer>
)

const ResponseChart = ({ data }: ChartProps) => (
  <ResponsiveContainer width="100%" height={400}>
    <LineChart data={data}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="time" />
      <YAxis />
      <Tooltip />
      <Line type="monotone" dataKey="responses" stroke="#82ca9d" name="Responses" />
    </LineChart>
  </ResponsiveContainer>
)

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

export function KindStats({ kindId }: { kindId: number }) {
  const [timeRange, setTimeRange] = useState<TimeWindow>('30d')
  const { stats, isLoading, isError } = useKindStats(kindId, timeRange)

  console.log('KindStats render:', { kindId, timeRange, isLoading, isError, hasStats: !!stats });

  if (isError) return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <p>Error loading kind stats</p>
    </div>
  )

  if (isLoading || !stats) return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <p>Loading...</p>
    </div>
  )

  // Transform time series data for charts
  const requestData = stats.time_series.map((point) => ({
    time: point.time,
    requests: point.running_total_requests
  }))

  const responseData = stats.time_series.map((point) => ({
    time: point.time,
    responses: point.running_total_responses
  }))

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
            <h1 className="text-xl font-bold">DVMDash Stats</h1>
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
          <div className="flex items-center">
            <TimeRangeSelector timeRange={timeRange} setTimeRange={setTimeRange} />
          </div>
        </div>
      </header>

      <div className="w-full bg-muted py-3">
        <div className="container mx-auto px-4 text-center">
          <p className="text-sm text-muted-foreground flex items-center justify-center">
            <Clock className="h-4 w-4 mr-1" />
            Data automatically updates every second
          </p>
        </div>
      </div>

      <main className="container mx-auto p-4">
        <div className="mb-6">
          <h2 className="text-2xl font-bold mb-2">Kind: {stats.kind}</h2>
          <p className="text-sm text-muted-foreground">
            Showing data from {stats.period_start.toLocaleString()} to {stats.period_end.toLocaleString()}
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Requests</CardTitle>
              <Hash className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.running_total_requests.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Total requests to date</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Supporting DVMs</CardTitle>
              <Bot className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.num_supporting_dvms.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">DVMs supporting this kind</p>
            </CardContent>
          </Card>
        </div>

        <Card className="mt-8">
          <CardHeader>
            <CardTitle>Total Activity Over Time</CardTitle>
          </CardHeader>
          <CardContent>
            <RequestChart data={requestData} />
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
