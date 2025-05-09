'use client'

import { useState, useMemo } from 'react'
import Link from 'next/link'
import { cn } from "@/lib/utils"
import { useDVMStats } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { ArrowLeft, BarChart3, Bot, Tags, Settings, FileText, ArrowDownToLine, Users, Server, Hash, Star, Zap, Target, Brain, Home, Clock } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
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

import type { TimeWindow, TimeRangeSelectorProps, ChartProps, NavIconProps, ChartData } from '@/lib/types'

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

const ActivityChart = ({ data, viewMode, timeRange }: { data: ChartData[], viewMode: ViewMode, timeRange: TimeWindow }) => {
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
          total_responses: 0,
          total_feedback: 0
        });
      }
      
      const existing = aggregatedData.get(timeKey);
      existing.total_responses += point.total_responses;
      existing.total_feedback += point.total_feedback;
    });

    let processedData = Array.from(aggregatedData.values());

    // Then calculate cumulative values if in cumulative mode
    if (viewMode === 'cumulative') {
      let responseSum = 0;
      let feedbackSum = 0;
      processedData = processedData.map(point => ({
        ...point,
        total_responses: (responseSum += Number(point.total_responses)),
        total_feedback: (feedbackSum += Number(point.total_feedback))
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
        <BarChart data={data}>
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
          formatter={(value, name, props) => {
            // Set the color based on the dataKey
            const color = props.dataKey === 'total_responses' ? '#8884d8' : '#82ca9d';
            // Return the value with the name
            return [<span style={{ color }}>{Number(value).toLocaleString()}</span>, name];
          }}
          wrapperStyle={{ pointerEvents: 'auto' }}
          contentStyle={{ 
            backgroundColor: 'rgba(255, 255, 255, 0.95)', 
            color: '#000', 
            border: '1px solid #ccc',
            boxShadow: '0 2px 4px rgba(0, 0, 0, 0.2)',
            padding: '8px',
            borderRadius: '4px'
          }}
          itemStyle={{ color: undefined }}
          labelStyle={{ color: '#000', fontWeight: 'bold' }}
        />
          <Legend />
          <Bar dataKey="total_responses" fill="#8884d8" name="Responses" />
          <Bar dataKey="total_feedback" fill="#82ca9d" name="Feedback" />
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
            formatter={(value, name, props) => {
              // Set the color based on the dataKey
              const color = props.dataKey === 'total_responses' ? '#8884d8' : '#82ca9d';
              // Return the value with the name
              return [<span style={{ color }}>{Number(value).toLocaleString()}</span>, name];
            }}
            wrapperStyle={{ pointerEvents: 'auto' }}
            contentStyle={{ 
              backgroundColor: 'rgba(255, 255, 255, 0.95)', 
              color: '#000', 
              border: '1px solid #ccc',
              boxShadow: '0 2px 4px rgba(0, 0, 0, 0.2)',
              padding: '8px',
              borderRadius: '4px'
            }}
            itemStyle={{ color: undefined }}
            labelStyle={{ color: '#000', fontWeight: 'bold' }}
          />
        <Legend />
        <Line 
          type="monotone" 
          dataKey="total_responses" 
          stroke="#8884d8" 
          name="Responses"
          strokeWidth={2}
        />
        <Line 
          type="monotone" 
          dataKey="total_feedback" 
          stroke="#82ca9d" 
          name="Feedback"
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

export function DVMStats({ dvmId }: { dvmId: string }) {
  const [timeRange, setTimeRange] = useState<TimeWindow>('30d')
  const [viewMode, setViewMode] = useState<ViewMode>('bar')
  const { stats, isLoading, isError } = useDVMStats(dvmId, timeRange)

  // Debug logging
  const DEBUG = process.env.NEXT_PUBLIC_LOG_LEVEL === 'DEBUG';
  if (DEBUG) {
    console.log('DVMStats render:', { dvmId, timeRange, isLoading, isError, hasStats: !!stats });
  }


  if (isError) return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <p>Error loading DVM stats</p>
    </div>
  )

  if (isLoading || !stats || !stats.total_responses) return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <p>{isLoading ? "Loading..." : "No stats available"}</p>
    </div>
  )

  const chartData = (stats.time_series || []).map(point => ({
    ...point,
    [point.time]: point.time,  // Add index signature requirement
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
          <div className="flex items-center space-x-2">
            <TimeRangeSelector timeRange={timeRange} setTimeRange={setTimeRange} />
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="container mx-auto p-4">
        <div className="mb-6">
          <div className="flex items-center gap-4 mb-2">
            {stats.dvm_picture && (
              <img 
                src={stats.dvm_picture} 
                alt={stats.dvm_name || stats.dvm_id} 
                className="w-12 h-12 rounded-full object-cover"
              />
            )}
            <h2 className="text-2xl font-bold">
              DVM: {stats.dvm_name || stats.dvm_id}
            </h2>
          </div>
          {stats.dvm_about && (
            <p className="text-sm text-muted-foreground mb-2">{stats.dvm_about}</p>
          )}
          <p className="text-sm text-muted-foreground">
            Showing data from {stats.period_start.toLocaleString()} to {stats.period_end.toLocaleString()}
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Responses</CardTitle>
              <Server className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_responses.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Total responses to date</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Feedback</CardTitle>
              <Star className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_feedback.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">Total feedback received to date</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Supported Kinds</CardTitle>
              <Tags className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.supported_kinds?.length.toLocaleString() ?? '0'}</div>
              <div className="mt-2">
                <div className="flex flex-wrap gap-2">
                  {stats.supported_kinds?.map((kind) => (
                    <Link 
                      key={kind} 
                      href={`/kind-stats/${kind}`}
                      className="inline-flex items-center px-2 py-1 rounded-md bg-muted hover:bg-muted/80 text-xs font-medium transition-colors"
                    >
                      {kind}
                    </Link>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <Card className="mt-8">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>DVM Activity</CardTitle>
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
            <ActivityChart data={chartData} viewMode={viewMode} timeRange={timeRange} />
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
