import type { FlightOption } from "./flight";

export interface PriceCalendarDate {
  min_price: number;
  max_price: number;
  option_count: number;
  has_direct?: boolean;
}

export interface PriceCalendar {
  dates: Record<string, PriceCalendarDate>;
  cheapest_date: string;
  preferred_date_rank: number;
  savings_if_flexible: number;
}

export interface SearchResult {
  search_id: string;
  leg: {
    origin: string;
    destination: string;
    preferred_date: string;
  };
  price_calendar: PriceCalendar;
  recommendation: FlightOption & { reason: string };
  alternatives: {
    cheaper_dates: FlightOption[];
    alternate_airports: FlightOption[];
    different_routing: FlightOption[];
  };
  all_options: FlightOption[];
  metadata: {
    total_options_found: number;
    airports_searched: string[];
    dates_searched: string[];
    cached: boolean;
    search_time_ms: number;
  };
}

// Month Calendar types

export interface MonthCalendarDate {
  min_price: number;
  has_direct: boolean;
  option_count: number;
}

export interface MonthCalendarData {
  dates: Record<string, MonthCalendarDate>;
  month_stats: {
    cheapest_price: number;
    cheapest_date: string | null;
    avg_price: number;
    dates_with_flights: number;
    dates_with_direct: number;
  };
}

// Price Advisor types

export interface PriceAdvisorFactor {
  name: string;
  impact: "positive" | "negative" | "neutral";
  detail: string;
}

export interface PriceAdvice {
  recommendation: "book" | "wait" | "watch";
  confidence: number;
  headline: string;
  analysis: string;
  factors: PriceAdvisorFactor[];
  timing_advice?: string;
  savings_potential?: string;
  source: "llm" | "fallback" | "disabled";
}

// Price Trend types

export interface PriceTrendPoint {
  date: string;
  price: number;
  most_expensive?: number | null;
  results_count?: number;
}

export interface PriceTrend {
  leg_trend: PriceTrendPoint[];
  route_history: PriceTrendPoint[];
  route: string;
  data_points: number;
}
