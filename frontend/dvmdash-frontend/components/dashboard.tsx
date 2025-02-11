'use client'

import { useState, useMemo } from 'react'
import Link from 'next/link'
import { cn } from "@/lib/utils"
import { useTimeWindowStats } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { ArrowLeft, BarChart3, Bot, Tags, Settings, FileText, ArrowDownToLine, Users, Server, Hash, Star, Zap, Target, Brain, Home, Clock } from 'lucide-react'
import type { TimeWindow, TimeRangeSelectorProps, ChartData, NavIconProps, TimeSeriesData } from '@/lib/types'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Legend
} from 'recharts'

type ViewMode = 'bar' | 'cumulative'

const TimeRangeSelector = ({ timeRange, setTimeRange }: TimeRangeSelectorProps) => (
  <Tabs value={timeRange} onValueChange={(value) => setTimeRange(value as TimeWindow)} className="w-full max-w-xs">
    <TabsList className="grid w-full grid-cols-4 h-9">
      <TabsTrigger value="1h" className="text-xs">1h</TabsTrigger>
      <TabsTrigger value="24h" className="text-xs">24h</TabsTrigger>
      <TabsTrigger value="7d" className="text-xs">7d</TabsTrigger>
      <TabsTrigger value="30d" className="text-xs">30d</TabsTrigger>
    </TabsList>
  </Tabs>
)

const formatRelativeTime = (timeStr: string, timeRange: TimeWindow, isTooltip: boolean = false): string => {
  const time = new Date(timeStr);

  switch (timeRange) {
    case '1h': {
      const hours = time.getUTCHours();
      const minutes = time.getUTCMinutes();
      return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
    }
    case '24h': {
      const hour = time.getUTCHours();
      const ampm = hour >= 12 ? 'PM' : 'AM';
      const hour12 = hour % 12 || 12;
      return `${hour12} ${ampm}`;
    }
    case '7d': {
      const month = time.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' });
      const day = time.getUTCDate();
      if (isTooltip) {
        const hour = time.getUTCHours();
        const ampm = hour >= 12 ? 'PM' : 'AM';
        const hour12 = hour % 12 || 12;
        return `${month} ${day} ${hour12} ${ampm}`;
      }
      return `${month} ${day}`;
    }
    case '30d': {
      const month = time.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' });
      const day = time.getUTCDate();
      return `${month} ${day}`;
    }
    default:
      return timeStr;
  }
};

const getXAxisInterval = (timeRange: TimeWindow): number => {
  switch (timeRange) {
    case '1h':
      return 5; // Show every 5 minutes
    case '24h':
      return 1; // Show every hour
    case '7d':
      return 24; // Show every day
    case '30d':
      return 1; // Show every day
    default:
      return 1;
  }
};

interface ChartComponentProps {
  data: ChartData[]
  viewMode: ViewMode
  timeRange: TimeWindow
}

const JobCountChart = ({ data, viewMode, timeRange }: ChartComponentProps) => {
  const chartData = useMemo(() => {
    // First aggregate data by timeKey if needed
    const aggregatedData = new Map();
    
    data.forEach(point => {
      const date = new Date(point.time);
      let timeKey;
      
      switch (timeRange) {
        case '1h':
          // Group by minute
          timeKey = new Date(date.setSeconds(0)).toISOString();
          break;
        case '24h':
          // Group by hour
          timeKey = new Date(date.setMinutes(0, 0, 0)).toISOString();
          break;
        case '7d':
        case '30d':
          // Group by day
          timeKey = new Date(date.setHours(0, 0, 0, 0)).toISOString();
          break;
        default:
          timeKey = point.time;
      }
      
      if (!aggregatedData.has(timeKey)) {
        aggregatedData.set(timeKey, {
          time: timeKey,
          requests: 0,
          responses: 0
        });
      }
      
      const existing = aggregatedData.get(timeKey);
      existing.requests += point.requests;
      existing.responses += point.responses;
    });

    let processedData = Array.from(aggregatedData.values());

    // Then calculate cumulative values if in cumulative mode
    if (viewMode === 'cumulative') {
      let requestsSum = 0;
      let responsesSum = 0;
      processedData = processedData.map(point => ({
        ...point,
        requests: (requestsSum += Number(point.requests)),
        responses: (responsesSum += Number(point.responses))
      }));
    }

    return processedData;
  }, [data, viewMode, timeRange]);

  // Get ticks for 7-day view (first data point of each day)
  const dayTicks = useMemo(() => {
    if (timeRange !== '7d') return undefined;
    
    const ticks: string[] = [];
    let currentDay: number | null = null;
    
    data.forEach(point => {
      const date = new Date(point.time);
      const day = date.getUTCDate();
      if (currentDay !== day) {
        currentDay = day;
        ticks.push(point.time);
      }
    });
    
    return ticks;
  }, [data, timeRange]);

  if (viewMode === 'bar') {
    return (
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis 
            dataKey="time"
            angle={-45}
            textAnchor="end"
            height={100}
            interval={timeRange === '7d' ? undefined : getXAxisInterval(timeRange)}
            ticks={timeRange === '7d' ? dayTicks : undefined}
            tickFormatter={(time) => formatRelativeTime(time, timeRange)}
            axisLine={true}
            orientation="bottom"
            padding={{ left: 30, right: 30 }}
          />
          <XAxis 
            dataKey="time"
            angle={-45}
            textAnchor="end"
            height={100}
            interval={timeRange === '7d' ? undefined : getXAxisInterval(timeRange)}
            ticks={timeRange === '7d' ? dayTicks : undefined}
            tickFormatter={(time) => formatRelativeTime(time, timeRange)}
            axisLine={true}
            orientation="top"
            padding={{ left: 30, right: 30 }}
          />
          <YAxis tickFormatter={(value) => Number(value).toLocaleString()} />
          <Tooltip 
            labelFormatter={(time) => formatRelativeTime(time as string, timeRange, true)}
            formatter={(value) => [Number(value).toLocaleString(), undefined]}
          />
          <Legend />
          <Bar dataKey="requests" fill="#8884d8" name="Requests" />
          <Bar dataKey="responses" fill="#82ca9d" name="Responses" />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis 
          dataKey="time"
          angle={-45}
          textAnchor="end"
          height={100}
          interval={timeRange === '7d' ? undefined : getXAxisInterval(timeRange)}
          ticks={timeRange === '7d' ? dayTicks : undefined}
          tickFormatter={(time) => formatRelativeTime(time, timeRange)}
          axisLine={true}
          orientation="bottom"
          padding={{ left: 30, right: 30 }}
        />
        <XAxis 
          dataKey="time"
          angle={-45}
          textAnchor="end"
          height={100}
          interval={timeRange === '7d' ? undefined : getXAxisInterval(timeRange)}
          ticks={timeRange === '7d' ? dayTicks : undefined}
          tickFormatter={(time) => formatRelativeTime(time, timeRange)}
          axisLine={true}
          orientation="top"
          padding={{ left: 30, right: 30 }}
        />
        <YAxis tickFormatter={(value) => Number(value).toLocaleString()} />
        <Tooltip 
          labelFormatter={(time) => formatRelativeTime(time as string, timeRange, true)}
          formatter={(value) => [Number(value).toLocaleString(), undefined]}
        />
        <Legend />
        <Line 
          type="monotone" 
          dataKey="requests" 
          stroke="#8884d8" 
          name="Cumulative Requests"
          strokeWidth={2}
        />
        <Line 
          type="monotone" 
          dataKey="responses" 
          stroke="#82ca9d" 
          name="Cumulative Responses"
          strokeWidth={2}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

const ActorCountChart = ({ data, viewMode, timeRange }: ChartComponentProps) => {
  const chartData = useMemo(() => {
    // First aggregate data by timeKey if needed
    const aggregatedData = new Map();
    
    data.forEach(point => {
      const date = new Date(point.time);
      let timeKey;
      
      switch (timeRange) {
        case '1h':
          // Group by minute
          timeKey = new Date(date.setSeconds(0)).toISOString();
          break;
        case '24h':
          // Group by hour
          timeKey = new Date(date.setMinutes(0, 0, 0)).toISOString();
          break;
        case '7d':
        case '30d':
          // Group by day
          timeKey = new Date(date.setHours(0, 0, 0, 0)).toISOString();
          break;
        default:
          timeKey = point.time;
      }
      
      if (!aggregatedData.has(timeKey)) {
        aggregatedData.set(timeKey, {
          time: timeKey,
          users: 0,
          agents: 0
        });
      }
      
      const existing = aggregatedData.get(timeKey);
      existing.users += point.users;
      existing.agents += point.agents;
    });

    let processedData = Array.from(aggregatedData.values());

    // Then calculate cumulative values if in cumulative mode
    if (viewMode === 'cumulative') {
      let usersSum = 0;
      let agentsSum = 0;
      processedData = processedData.map(point => ({
        ...point,
        users: (usersSum += Number(point.users)),
        agents: (agentsSum += Number(point.agents))
      }));
    }

    return processedData;
  }, [data, viewMode, timeRange]);

  // Get ticks for 7-day view (first data point of each day)
  const dayTicks = useMemo(() => {
    if (timeRange !== '7d') return undefined;
    
    const ticks: string[] = [];
    let currentDay: number | null = null;
    
    data.forEach(point => {
      const date = new Date(point.time);
      const day = date.getUTCDate();
      if (currentDay !== day) {
        currentDay = day;
        ticks.push(point.time);
      }
    });
    
    return ticks;
  }, [data, timeRange]);

  if (viewMode === 'bar') {
    return (
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis 
            dataKey="time"
            angle={-45}
            textAnchor="end"
            height={100}
            interval={timeRange === '7d' ? undefined : getXAxisInterval(timeRange)}
            ticks={timeRange === '7d' ? dayTicks : undefined}
            tickFormatter={(time) => formatRelativeTime(time, timeRange)}
            axisLine={true}
            orientation="bottom"
            padding={{ left: 30, right: 30 }}
          />
          <XAxis 
            dataKey="time"
            angle={-45}
            textAnchor="end"
            height={100}
            interval={timeRange === '7d' ? undefined : getXAxisInterval(timeRange)}
            ticks={timeRange === '7d' ? dayTicks : undefined}
            tickFormatter={(time) => formatRelativeTime(time, timeRange)}
            axisLine={true}
            orientation="top"
            padding={{ left: 30, right: 30 }}
          />
          <YAxis tickFormatter={(value) => Number(value).toLocaleString()} />
          <Tooltip 
            labelFormatter={(time) => formatRelativeTime(time as string, timeRange, true)}
            formatter={(value) => [Number(value).toLocaleString(), undefined]}
          />
          <Legend />
          <Bar dataKey="users" fill="#8884d8" name="Users" />
          <Bar dataKey="agents" fill="#82ca9d" name="DVMs" />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis 
          dataKey="time"
          angle={-45}
          textAnchor="end"
          height={100}
          interval={timeRange === '7d' ? undefined : getXAxisInterval(timeRange)}
          ticks={timeRange === '7d' ? dayTicks : undefined}
          tickFormatter={(time) => formatRelativeTime(time, timeRange)}
          axisLine={true}
          orientation="bottom"
          padding={{ left: 30, right: 30 }}
        />
        <XAxis 
          dataKey="time"
          angle={-45}
          textAnchor="end"
          height={100}
          interval={timeRange === '7d' ? undefined : getXAxisInterval(timeRange)}
          ticks={timeRange === '7d' ? dayTicks : undefined}
          tickFormatter={(time) => formatRelativeTime(time, timeRange)}
          axisLine={true}
          orientation="top"
          padding={{ left: 30, right: 30 }}
        />
        <YAxis tickFormatter={(value) => Number(value).toLocaleString()} />
        <Tooltip 
          labelFormatter={(time) => formatRelativeTime(time as string, timeRange, true)}
          formatter={(value) => [Number(value).toLocaleString(), undefined]}
        />
        <Legend />
        <Line 
          type="monotone" 
          dataKey="users" 
          stroke="#8884d8" 
          name="Cumulative Users"
          strokeWidth={2}
        />
        <Line 
          type="monotone" 
          dataKey="agents" 
          stroke="#82ca9d" 
          name="Cumulative DVMs"
          strokeWidth={2}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

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

export function Dashboard() {
  const [timeRange, setTimeRange] = useState<TimeWindow>('30d')
  const [viewMode, setViewMode] = useState<ViewMode>('bar')
  const { stats, isLoading, isError } = useTimeWindowStats(timeRange)

  if (isError) return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <p>Error loading stats</p>
    </div>
  )

  if (isLoading) return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <p>Loading...</p>
    </div>
  )

  if (!stats) return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <p>No stats available</p>
    </div>
  )

  // Transform time series data for charts
  const jobCountData = stats.time_series.map((point: TimeSeriesData) => ({
    time: point.time,
    requests: point.total_requests,
    responses: point.total_responses
  }))

  const actorCountData = stats.time_series.map((point: TimeSeriesData) => ({
    time: point.time,
    users: point.unique_users,
    agents: point.unique_dvms
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
                isActive={true}
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
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Job Requests</CardTitle>
              <FileText className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_requests.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Total requests processed</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Job Responses</CardTitle>
              <ArrowDownToLine className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_responses.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">
                {((stats.total_responses / stats.total_requests) * 100).toFixed(1)}% completion rate
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Unique Users</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.unique_users.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Active users in period</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Unique DVMs</CardTitle>
              <Server className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.unique_dvms.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Active DVMs in period</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Unique Kinds</CardTitle>
              <Hash className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.unique_kinds}</div>
              <p className="text-xs text-muted-foreground">Different kinds available</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Most Popular DVM</CardTitle>
              <Star className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold truncate" title={stats.popular_dvm || 'None'}>
                {stats.popular_dvm ? stats.popular_dvm.slice(0, 8) + '...' : 'None'}
              </div>
              <p className="text-xs text-muted-foreground">Most used DVM</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Popular Kind</CardTitle>
              <Zap className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.popular_kind || 'None'}</div>
              <p className="text-xs text-muted-foreground">Most requested kind</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Competitive Kind</CardTitle>
              <Target className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.competitive_kind || 'None'}</div>
              <p className="text-xs text-muted-foreground">Most DVMs competing</p>
            </CardContent>
          </Card>
        </div>

        <Card className="mt-8">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Network Activity</CardTitle>
            <div className="flex items-center space-x-2">
              <Button
                variant={viewMode === 'bar' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setViewMode('bar')}
              >
                Bar
              </Button>
              <Button
                variant={viewMode === 'cumulative' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setViewMode('cumulative')}
              >
                Cumulative
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="jobCount">
              <TabsList className="mb-4">
                <TabsTrigger value="jobCount">Job Count</TabsTrigger>
                <TabsTrigger value="actorCount">Actor Count</TabsTrigger>
              </TabsList>
              <TabsContent value="jobCount">
                <JobCountChart data={jobCountData} viewMode={viewMode} timeRange={timeRange} />
              </TabsContent>
              <TabsContent value="actorCount">
                <ActorCountChart data={actorCountData} viewMode={viewMode} timeRange={timeRange} />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
