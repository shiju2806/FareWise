import type { EventData } from "./event";

export interface BundleOption {
  departure_date: string;
  check_in: string;
  check_out: string;
  flight_cost: number;
  hotel_nightly: number;
  hotel_total: number;
  combined_total: number;
  per_night_total: number;
  events: string[];
  is_preferred: boolean;
  strategy?: string;
  label?: string;
  savings_vs_preferred?: number;
}

export interface BundleResult {
  trip_leg_id: string;
  origin: string;
  destination: string;
  bundles: BundleOption[];
  date_matrix: BundleOption[];
  events: EventData[];
  hotel_nights: number;
  preferred_date: string;
}
