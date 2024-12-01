'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { Activity, Brain, Cpu, Network, Settings, Zap } from 'lucide-react'

export default function Component() {
  const [timeRange, setTimeRange] = useState('1h')

  // Sample data - replace with real data from your Nostr API
  const mockData = Array.from({ length: 24 }, (_, i) => ({
    time: `${i}:00`,
    activeAgents: Math.floor(Math.random() * 1000) + 500,
    memoryUsage: Math.floor(Math.random() * 2000) + 1000,
    transactions: Math.floor(Math.random() * 3000) + 1000,
  }))

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container flex h-16 items-center justify-between px-4">
          <div className="flex items-center space-x-4">
            <Brain className="h-6 w-6" />
            <h1 className="text-xl font-bold">Nostr AI Dashboard</h1>
          </div>
          <div className="flex items-center space-x-4">
            <Button variant="outline" size="sm">
              Connect Wallet
            </Button>
            <Button variant="ghost" size="icon">
              <Settings className="h-5 w-5" />
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto p-4">
        <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Active AI Agents</CardTitle>
              <Activity className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">2,345</div>
              <p className="text-xs text-muted-foreground">+20.1% from last hour</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Memory Usage</CardTitle>
              <Cpu className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">1.2 TB</div>
              <p className="text-xs text-muted-foreground">+2.5% from last hour</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Network Load</CardTitle>
              <Network className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">4.2k req/s</div>
              <p className="text-xs text-muted-foreground">-0.3% from last hour</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Processing Power</CardTitle>
              <Zap className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">89.2%</div>
              <p className="text-xs text-muted-foreground">+5.2% from last hour</p>
            </CardContent>
          </Card>
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Card className="col-span-2">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Network Activity</CardTitle>
                <Tabs defaultValue="1h" className="w-[300px]">
                  <TabsList>
                    <TabsTrigger value="1h" onClick={() => setTimeRange('1h')}>1h</TabsTrigger>
                    <TabsTrigger value="24h" onClick={() => setTimeRange('24h')}>24h</TabsTrigger>
                    <TabsTrigger value="7d" onClick={() => setTimeRange('7d')}>7d</TabsTrigger>
                    <TabsTrigger value="30d" onClick={() => setTimeRange('30d')}>30d</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
            </CardHeader>
            <CardContent>
              <div className="h-[400px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={mockData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" />
                    <YAxis />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey="activeAgents"
                      stroke="#8884d8"
                      name="Active Agents"
                    />
                    <Line
                      type="monotone"
                      dataKey="memoryUsage"
                      stroke="#82ca9d"
                      name="Memory Usage"
                    />
                    <Line
                      type="monotone"
                      dataKey="transactions"
                      stroke="#ffc658"
                      name="Transactions"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  )
}