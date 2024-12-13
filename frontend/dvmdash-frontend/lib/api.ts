// lib/api.ts
import useSWR from 'swr'

const fetcher = (url: string) =>
  fetch(url)
    .then(res => res.json())
    .then(data => ({
      ...data,
      timestamp: new Date(data.timestamp),
      period_start: new Date(data.period_start),
      period_end: new Date(data.period_end),
    }));

export function useGlobalStats(timeRange: string) {
  const { data, error, isLoading } = useSWR(
    `http://localhost:8000/api/stats/global/latest?timeRange=${timeRange}`,
    fetcher,
    { refreshInterval: 1000 } // Refresh every second
  )

  return {
    stats: data,
    isLoading,
    isError: error
  }
}
