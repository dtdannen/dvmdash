'use client'

import { useState } from 'react'
import Link from 'next/link'
import { cn } from "@/lib/utils"
import { useDVMStats } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { ArrowLeft, BarChart3, Bot, Tags, Settings, FileText, ArrowDownToLine, Users, Server, Hash, Star, Zap, Target, Brain, Home, Clock, ThumbsUp } from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

const TimeRangeSelector = ({ timeRange, setTimeRange }) => (
  <Tabs value={timeRange} onValueChange={setTimeRange} className="w-full max-w-xs">
    <TabsList className="grid w-full grid-cols-5 h-9">
      <TabsTrigger value="1h" className="text-xs">1h</TabsTrigger>
      <TabsTrigger value="24h" className="text-xs">24h</TabsTrigger>
      <TabsTrigger value="7d" className="text-xs">7d</TabsTrigger>
      <TabsTrigger value="30d" className="text-xs">30d</TabsTrigger>
    </TabsList>
  </Tabs>
)

const ResponseChart = ({ data }) => (
  <ResponsiveContainer width="100%" height={400}>
    <LineChart data={data}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="time" />
      <YAxis />
      <Tooltip />
      <Line type="monotone" dataKey="responses" stroke="#8884d8" name="Responses" />
    </LineChart>
  </ResponsiveContainer>
)

const FeedbackChart = ({ data }) => (
  <ResponsiveContainer width="100%" height={400}>
    <LineChart data={data}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="time" />
      <YAxis />
      <Tooltip />
      <Line type="monotone" dataKey="feedback" stroke="#82ca9d" name="Feedback" />
    </LineChart>
  </ResponsiveContainer>
)

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

export function DVMStats({ dvmId }: { dvmId: string }) {
  const [timeRange, setTimeRange] = useState('30d')
  const { stats, isLoading, isError } = useDVMStats(dvmId, timeRange)

  console.log('DVMStats render:', { dvmId, timeRange, isLoading, isError, hasStats: !!stats });


  if (isError) return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <p>Error loading DVM stats</p>
    </div>
  )

  if (isLoading || !stats) return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <p>Loading...</p>
    </div>
  )

  // Transform time series data for charts
  const responseData = stats.time_series.map(point => ({
    time: point.time,
    responses: point.period_responses
  }))

  const feedbackData = stats.time_series.map(point => ({
    time: point.time,
    feedback: point.period_feedback
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
          <h2 className="text-2xl font-bold mb-2">DVM: {stats.dvm_id}</h2>
          <p className="text-sm text-muted-foreground">
            Showing data from {stats.period_start.toLocaleString()} to {stats.period_end.toLocaleString()}
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Period Responses</CardTitle>
              <ArrowDownToLine className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.period_responses.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Responses in current period</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Period Feedback</CardTitle>
              <ThumbsUp className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.period_feedback.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Feedback received in current period</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Responses</CardTitle>
              <Server className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.running_total_responses.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Total responses to date</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Feedback</CardTitle>
              <Star className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.running_total_feedback.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Total feedback received to date</p>
            </CardContent>
          </Card>
        </div>

        <Card className="mt-8">
          <CardHeader>
            <CardTitle>DVM Activity</CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="responses">
              <TabsList className="mb-4">
                <TabsTrigger value="responses">Responses</TabsTrigger>
                <TabsTrigger value="feedback">Feedback</TabsTrigger>
              </TabsList>
              <TabsContent value="responses">
                <ResponseChart data={responseData} />
              </TabsContent>
              <TabsContent value="feedback">
                <FeedbackChart data={feedbackData} />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </main>
    </div>
  )
}