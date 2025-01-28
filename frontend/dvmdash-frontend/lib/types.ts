// lib/types.ts
export interface TimeSeriesData {
  time: string;
  total_requests: number;
  unique_users: number;
  unique_dvms: number;
}

export interface TimeWindowStats {
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

export interface DVMTimeSeriesData {
  time: string;
  period_feedback: number;
  period_responses: number;
  running_total_feedback: number;
  running_total_responses: number;
}

export interface DVMStats {
  dvm_id: string;
  timestamp: Date;
  period_start: Date;
  period_end: Date;
  period_feedback: number;
  period_responses: number;
  running_total_feedback: number;
  running_total_responses: number;
  time_series: DVMTimeSeriesData[];
}

export interface DVMListItem {
  dvm_id: string;
  last_seen: Date;
  total_responses: number;
  total_feedback: number;
}

export interface DVMList {
  dvms: DVMListItem[];
}