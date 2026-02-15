export interface FlightOption {
  id: string;
  airline_code: string;
  airline_name: string;
  flight_numbers: string;
  origin_airport: string;
  destination_airport: string;
  departure_time: string;
  arrival_time: string;
  duration_minutes: number;
  stops: number;
  stop_airports: string | null;
  price: number;
  currency: string;
  cabin_class: string | null;
  seats_remaining: number | null;
  is_alternate_airport: boolean;
  is_alternate_date: boolean;
  within_flexibility?: boolean;
  score?: number;
}
