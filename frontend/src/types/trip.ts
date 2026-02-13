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
}

export interface Trip {
  id: string;
  title: string | null;
  status: string;
  natural_language_input: string | null;
  parsed_input: Record<string, unknown> | null;
  total_estimated_cost: number | null;
  currency: string;
  legs: TripLeg[];
  created_at: string;
  updated_at: string;
}
