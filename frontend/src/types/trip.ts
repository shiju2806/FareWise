export interface TripLeg {
  id: string;
  sequence: number;
  origin_airport: string;
  origin_city: string;
  destination_airport: string;
  destination_city: string;
  preferred_date: string;
  flexibility_days: number;
  cabin_class: string;
  passengers: number;
  companion_preferred_date: string | null;
}

export interface Trip {
  id: string;
  title: string | null;
  status: string;
  natural_language_input: string | null;
  parsed_input: Record<string, unknown> | null;
  total_estimated_cost: number | null;
  currency: string;
  companions: number;
  companion_cabin_class: string | null;
  legs: TripLeg[];
  created_at: string;
  updated_at: string;
}

export interface CompanionLegOption {
  leg_id: string;
  route: string;
  date: string;
  cabin_class: string;
  airline_code: string;
  airline_name: string;
  per_person: number;
  total: number;
  stops: number;
  duration_minutes: number;
}

export interface NearbyDateOption {
  leg_id: string;
  route: string;
  date: string;
  cabin_class: string;
  airline_code: string;
  airline_name: string;
  per_person: number;
  total: number;
  stops: number;
  date_diff_days: number;
  savings_vs_selected: number;
}

export interface CompanionPricing {
  employee_total: number;
  companions_count: number;
  companion_cabin_class: string;
  companion_options: CompanionLegOption[];
  nearby_date_options: NearbyDateOption[];
  combined_min: number;
  combined_max: number;
  summary: string;
}

export interface CabinOption {
  cabin_class: string;
  per_person_per_leg: number[];
  total_per_person: number;
  total_all_travelers: number;
  fits_budget: boolean;
  budget_delta: number;
  budget_delta_percent: number;
  airline_codes: string[];
}

export interface CabinBudgetResult {
  anchor_total: number;
  budget_envelope: number;
  budget_tolerance: number;
  total_travelers: number;
  recommended_cabin: string;
  recommendation_reason: string;
  cabin_options: CabinOption[];
  economy_savings: number;
  near_miss_note?: string | null;
  savings_note?: string | null;
  source: "llm" | "fallback";
}
