import type { FlightOption } from "./flight";

export interface PriceCalendarDate {
  min_price: number;
  max_price: number;
  option_count: number;
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
