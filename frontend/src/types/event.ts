export interface EventData {
  external_id: string;
  title: string;
  category: string;
  labels: string[];
  start_date: string;
  end_date: string;
  city: string;
  country: string | null;
  latitude: number | null;
  longitude: number | null;
  venue_name: string | null;
  rank: number;
  local_rank: number | null;
  attendance: number | null;
  icon: string;
  impact_level: "low" | "medium" | "high" | "very_high";
  price_increase_pct: number;
}

export interface DateEvent {
  title: string;
  category: string;
  icon: string;
  impact_level: "low" | "medium" | "high" | "very_high";
  price_increase_pct: number;
  attendance: number | null;
}

export interface EventSummary {
  total_events: number;
  highest_impact_event: string | null;
  peak_impact_dates: string[];
  recommendation: string | null;
}

export interface LegEventsResponse {
  trip_leg_id: string;
  destination: string;
  preferred_date: string;
  events: EventData[];
  date_events: Record<string, DateEvent[]>;
  summary: EventSummary;
}
