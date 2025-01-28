// lib/api.ts
import useSWR from 'swr'

const fetcher = (url: string) =>
  fetch(url)
    .then(res => {
      if (!res.ok) throw new Error('API request failed')
      return res.json()
    })
    .then(data => ({
      ...data,
      timestamp: new Date(data.timestamp),
      period_start: new Date(data.period_start),
      period_end: new Date(data.period_end),
    }));

// Add a new hook for fetching DVM stats
export function useDVMStats(dvmId: string, timeRange: string) {

    console.log(`Making request to: http://localhost:8000/api/stats/dvm/${dvmId}?timeRange=${timeRange}`);
  const { data, error, isLoading } = useSWR(
    dvmId ? `http://localhost:8000/api/stats/dvm/${dvmId}?timeRange=${timeRange}` : null,
    fetcher,
    { refreshInterval: 1000, // Refresh every second
        onError: (err) => console.error('SWR Error:', err)}
  );

  return {
    stats: data,
    isLoading,
    isError: error
  };
}

export function useTimeWindowStats(timeRange: string) {
  const { data, error, isLoading } = useSWR(
    `http://localhost:8000/api/stats/global/latest?timeRange=${timeRange}`,
    fetcher,
    {
      refreshInterval: 1000,
      onError: (err) => console.error('SWR Error:', err)
    }
  )

  return {
    stats: data,
    isLoading,
    isError: error
  }
}
