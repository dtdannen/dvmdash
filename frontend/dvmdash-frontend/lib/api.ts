import useSWR from 'swr'
import { TimeWindow, TimeWindowStats } from './types'

// Debug mode flag
const DEBUG = process.env.NEXT_PUBLIC_LOG_LEVEL === 'DEBUG';

// Debug logging function
const debugLog = (...args: any[]) => {
  if (DEBUG) {
    console.log(...args);
  }
};

// Determine if we should use the proxy based on environment
const useProxy = typeof window !== 'undefined' && process.env.NEXT_PUBLIC_USE_API_PROXY === 'true'

// Determine the API base URL based on environment
const determineApiBase = () => {
  // Get environment variables
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  const metadataApiUrl = process.env.NEXT_PUBLIC_METADATA_API_URL;
  const isServer = typeof window === 'undefined';
  
  // For server-side rendering, use the metadata API URL
  if (isServer) {
    const serverUrl = metadataApiUrl || 'http://api:8000'; // Default to Docker service name
    debugLog('API_BASE determination (server-side):', {
      NEXT_PUBLIC_METADATA_API_URL: metadataApiUrl,
      serverUrl
    });
    return serverUrl;
  }
  
  // For client-side in browser, use the public API URL
  if (apiUrl) {
    debugLog('API_BASE determination (client-side):', {
      NEXT_PUBLIC_API_URL: apiUrl
    });
    return apiUrl;
  }
  
  // Fallback for development (should be avoided in production by setting env vars)
  console.warn('NEXT_PUBLIC_API_URL not set, falling back to localhost:8000');
  return 'http://localhost:8000';
};

export const API_BASE = determineApiBase();

/**
 * Standardized function to get the API URL for a given path
 * This ensures consistent API URL handling across the application
 */
export function getApiUrl(path: string): string {
  const baseUrl = API_BASE
  return `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`
}

/**
 * Convert a direct API URL to a proxy URL if needed
 * @param url The original API URL
 * @returns The URL to use (either direct or proxied)
 */
const getProxyUrl = (url: string): string => {
  // Only proxy if in browser and proxy is enabled
  if (!useProxy) return url
  
  // Extract the path and query from the URL
  const apiUrlObj = new URL(url)
  const apiPath = apiUrlObj.pathname.replace(/^\/api\//, '')
  
  // Build the proxy URL with the path parameter
  const proxyUrlObj = new URL('/api/proxy', window.location.origin)
  proxyUrlObj.searchParams.set('path', apiPath)
  
  // Copy all query parameters from the original URL
  apiUrlObj.searchParams.forEach((value, key) => {
    proxyUrlObj.searchParams.set(key, value)
  })
  
  debugLog(`Proxying request: ${url} -> ${proxyUrlObj.toString()}`)
  return proxyUrlObj.toString()
}

const fetcher = async (url: string) => {
  try {
    // Determine if we need to use the proxy
    const fetchUrl = useProxy ? getProxyUrl(url) : url
    
    debugLog('Fetching:', fetchUrl, useProxy ? `(proxied from ${url})` : '')
    const res = await fetch(fetchUrl, {
      mode: 'cors',
      headers: {
        'Accept': 'application/json'
      }
    })
    
    if (!res.ok) {
      console.error('API Error:', {
        url,
        status: res.status,
        statusText: res.statusText,
        headers: Object.fromEntries(res.headers.entries())
      })
      throw new Error(`API error: ${res.status} ${res.statusText}`)
    }

    const data = await res.json()
    debugLog('API Success:', {
      url,
      status: res.status,
      headers: Object.fromEntries(res.headers.entries()),
      data
    })
    return data
  } catch (error) {
    console.error('API Request Failed:', {
      url,
      error: error instanceof Error ? error.message : 'Unknown error',
      stack: error instanceof Error ? error.stack : undefined
    })
    throw error
  }
}

export interface DVMTimeSeriesData {
  time: string
  total_responses: number
  total_feedback: number
}

export interface DVMStats {
  dvm_id: string
  dvm_name?: string
  dvm_about?: string
  dvm_picture?: string
  timestamp: string
  period_start: string
  period_end: string
  total_responses: number
  total_feedback: number
  supported_kinds?: number[]
  time_series: DVMTimeSeriesData[]
}

export interface KindTimeSeriesData {
  time: string
  total_requests: number
  total_responses: number
}

export interface KindStats {
  kind: number
  timestamp: string
  period_start: string
  period_end: string
  total_requests: number
  total_responses: number
  num_supporting_dvms: number
  supporting_dvms: string[]
  time_series: KindTimeSeriesData[]
}

export function useDVMStats(dvmId: string, timeRange: TimeWindow) {
  const { data, error, isLoading } = useSWR<DVMStats>(
    `${API_BASE}/api/stats/dvm/${dvmId}${timeRange ? `?timeRange=${timeRange}` : ''}`,
    fetcher,
    {
      refreshInterval: 60000, // Update every 60 seconds
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
    `${API_BASE}/api/stats/kind/${kindId}${timeRange ? `?timeRange=${timeRange}` : ''}`,
    fetcher,
    {
      refreshInterval: 60000, // Update every 60 seconds
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
    timeRange ? `${API_BASE}/api/stats/global/latest${timeRange ? `?timeRange=${timeRange}` : ''}` : null,
    fetcher,
    {
      refreshInterval: 60000, // Update every 60 seconds
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
    `${API_BASE}/api/dvms${timeRange ? `?timeRange=${timeRange}&` : '?'}limit=${limit}&offset=${offset}`,
    fetcher,
    {
      refreshInterval: 60000, // Update every 60 seconds
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
    `${API_BASE}/api/kinds${timeRange ? `?timeRange=${timeRange}&` : '?'}limit=${limit}&offset=${offset}`,
    fetcher,
    {
      refreshInterval: 60000, // Update every 60 seconds
      onError: (err) => console.error('SWR Error:', err)
    }
  );

  return {
    kindList: data,
    isLoading,
    isError: error
  };
}
