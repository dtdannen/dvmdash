// lib/types.ts
export interface TimeSeriesData {
  time: string;
  total_requests: number;
  unique_users: number;
  unique_dvms: number;
}

export interface GlobalStats {
  timestamp: Date;
  period_start: Date;
  period_end: Date;
  total_requests: number;
  total_responses: number;
  unique_dvms: number;
  unique_kinds: number;
  unique_users: number;
  popular_dvm: string | null;
  popular_kind: number | null;
  competitive_kind: number | null;
  time_series: TimeSeriesData[];
}