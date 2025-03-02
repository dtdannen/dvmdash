export type TimeWindow = '1h' | '24h' | '7d' | '30d'

export interface ChartData {
  time: string
  [key: string]: string | number
}

export interface TimeRangeSelectorProps {
  timeRange: TimeWindow
  setTimeRange: (value: TimeWindow) => void
}

export interface ChartProps {
  data: ChartData[]
}

export interface NavIconProps {
  Icon: React.ComponentType<any>
  href: string
  isActive: boolean
  label: string
}

// lib/types.ts
export interface TimeSeriesData {
  time: string;
  total_requests: number;
  total_responses: number;
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
  total_responses: number;
  total_feedback: number;
}

export interface DVMProfileData {
  name?: string;
  display_name?: string;
  about?: string;
  picture?: string;
  banner?: string;
  website?: string;
  lud16?: string;
  nip05?: string;
  encryptionSupported?: boolean;
  cashuAccepted?: boolean;
  nip90Params?: Record<string, {
    required: boolean;
    values?: string[];
  }>;
}

export interface DVMStats {
  dvm_id: string;
  timestamp: Date;
  period_start: Date;
  period_end: Date;
  total_responses: number;
  total_feedback: number;
  supported_kinds: number[];
  time_series: DVMTimeSeriesData[];
  profile?: DVMProfileData;
}

export interface DVMListItem {
  id: string;
  last_seen: Date;
  total_requests?: number;
  total_responses?: number;
  total_feedback?: number;
  total_events?: number;
  supported_kinds: number[];
  num_supporting_kinds: number;
  is_active: boolean;
}

export interface DVMList {
  dvms: DVMListItem[];
}

export interface KindTimeSeriesData {
  time: string;
  total_requests: number;
  total_responses: number;
}

export interface KindStats {
  kind: number;
  timestamp: Date;
  period_start: Date;
  period_end: Date;
  total_requests: number;
  total_responses: number;
  num_supporting_dvms: number;
  supporting_dvms: string[];
  time_series: KindTimeSeriesData[];
}

export interface KindListItem {
  kind: number;
  total_requests?: number;
  total_responses?: number;
  num_supporting_dvms: number;
  last_seen: Date;
}

export interface KindListResponse {
  kinds: KindListItem[];
}
