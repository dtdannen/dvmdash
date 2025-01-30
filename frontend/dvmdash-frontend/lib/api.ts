import useSWR from 'swr'
import { TimeWindow, TimeWindowStats } from './types'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const fetcher = (url: string) => fetch(url).then(res => res.json())

export interface DVMTimeSeriesData {
  time: string
  total_responses: number
  total_feedback: number
}

export interface DVMStats {
  dvm_id: string
  timestamp: string
  period_start: string
  period_end: string
  total_responses: number
  total_feedback: number
  time_series: DVMTimeSeriesData[]
}

export interface KindTimeSeriesData {
  time: string
  running_total_requests: number
  running_total_responses: number
}

export interface KindStats {
  kind: number
  timestamp: string
  period_start: string
  period_end: string
  running_total_requests: number
  running_total_responses: number
  num_supporting_dvms: number
  supporting_dvms: string[]
  time_series: KindTimeSeriesData[]
}

export function useDVMStats(dvmId: string, timeRange: TimeWindow) {
  const { data, error, isLoading } = useSWR<DVMStats>(
    `${API_BASE}/api/stats/dvm/${dvmId}?timeRange=${timeRange}`,
    fetcher,
    {
      refreshInterval: 1000, // Update every second
    }
  )

  return {
    stats: data ? {
      ...data,
      timestamp: new Date(data.timestamp),
      period_start: new Date(data.period_start),
      period_end: new Date(data.period_end),
    } : null,
    isLoading,
    isError: error
  }
}

export function useKindStats(kindId: number, timeRange: TimeWindow) {
  const { data, error, isLoading } = useSWR<KindStats>(
    `${API_BASE}/api/stats/kind/${kindId}?timeRange=${timeRange}`,
    fetcher,
    {
      refreshInterval: 1000, // Update every second
    }
  )

  return {
    stats: data ? {
      ...data,
      timestamp: new Date(data.timestamp),
      period_start: new Date(data.period_start),
      period_end: new Date(data.period_end),
    } : null,
    isLoading,
    isError: error
  }
}

export function useTimeWindowStats(timeRange: TimeWindow) {
  const { data, error, isLoading } = useSWR<TimeWindowStats>(
    timeRange ? `${API_BASE}/api/stats/global/latest?timeRange=${timeRange}` : null,
    fetcher,
    {
      refreshInterval: 1000, // Update every second
    }
  )

  return {
    stats: data ? {
      ...data,
      timestamp: new Date(data.timestamp),
      period_start: new Date(data.period_start),
      period_end: new Date(data.period_end),
    } : null,
    isLoading,
    isError: error
  }
}

export function useDVMList(limit: number = 100, offset: number = 0, timeRange?: TimeWindow) {
  const { data, error, isLoading } = useSWR(
    `${API_BASE}/api/dvms?limit=${limit}&offset=${offset}${timeRange ? `&timeRange=${timeRange}` : ''}`,
    fetcher,
    {
      refreshInterval: 1000,
      onError: (err) => console.error('SWR Error:', err)
    }
  );

  return {
    dvmList: data,
    isLoading,
    isError: error
  };
}

export function useKindList(limit: number = 100, offset: number = 0, timeRange?: TimeWindow) {
  const { data, error, isLoading } = useSWR(
    `${API_BASE}/api/kinds?limit=${limit}&offset=${offset}${timeRange ? `&timeRange=${timeRange}` : ''}`,
    fetcher,
    {
      refreshInterval: 1000,
      onError: (err) => console.error('SWR Error:', err)
    }
  );

  return {
    kindList: data,
    isLoading,
    isError: error
  };
}
