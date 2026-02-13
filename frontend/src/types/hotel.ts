export interface HotelOption {
  id: string;
  hotel_name: string;
  hotel_chain: string | null;
  star_rating: number | null;
  user_rating: number | null;
  address: string | null;
  distance_km: number | null;
  nightly_rate: number;
  total_rate: number;
  currency: string;
  room_type: string | null;
  amenities: string[];
  cancellation_policy: string | null;
  is_preferred_vendor: boolean;
  neighborhood: string;
  score?: number;
}

export interface AreaComparison {
  area: string;
  avg_rate: number;
  min_rate: number;
  max_rate: number;
  option_count: number;
}

export interface HotelPriceCalendarEntry {
  check_in: string;
  check_out: string;
  nightly_rate: number;
  total_rate: number;
  is_preferred: boolean;
}

export interface EventWarning {
  title: string;
  category: string;
  impact_level: string;
  dates: string;
  message: string;
}

export interface HotelSearchResult {
  search_id: string;
  destination: string;
  check_in: string;
  check_out: string;
  nights: number;
  guests: number;
  recommendation: HotelOption | null;
  all_options: HotelOption[];
  area_comparison: AreaComparison[];
  event_warnings: EventWarning[];
  price_calendar: HotelPriceCalendarEntry[];
  metadata: {
    total_options: number;
    cheapest_rate: number | null;
    most_expensive_rate: number | null;
  };
}
