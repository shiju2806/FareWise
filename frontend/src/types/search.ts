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
    same_airline_cheaper: FlightOption[];
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

// Price Context types (historical quartiles)

export interface PriceMetrics {
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
}

export interface PriceContext {
  available: boolean;
  route?: string;
  date?: string;
  historical?: PriceMetrics;
  current_price?: number | null;
  percentile?: number | null;
  percentile_label?: "excellent" | "good" | "average" | "high" | null;
  message?: string;
}

// Airline×Date matrix entry from DB1B calendar data
export interface MatrixEntry {
  airline_code: string;
  airline_name: string;
  date: string;
  price: number;
  stops: number;
}

// Trip-window alternatives (preserve trip duration, shift dates)
export interface TripWindowFlight {
  airline_name: string;
  airline_code: string;
  price: number;
  stops: number;
  departure_time?: string;
  arrival_time?: string;
  duration_minutes?: number;
}

export interface TripWindowProposal {
  outbound_date: string;
  return_date: string;
  trip_duration: number;
  /** How many days longer/shorter than original (+1, -2, etc.) */
  duration_change?: number;
  outbound_flight: TripWindowFlight;
  return_flight: TripWindowFlight;
  total_price: number;
  savings: number;
  savings_percent: number;
  same_airline: boolean;
  airline_name: string | null;
  user_airline?: boolean;
  /** LLM-generated reason why this proposal is worth considering */
  reason?: string;
}

export interface TripWindowAlternatives {
  original_trip_duration: number;
  original_total_price: number;
  proposals: TripWindowProposal[];
  /** LLM-categorized proposals for significantly shifted dates (different month) */
  different_month?: TripWindowProposal[];
}
