export interface PriceWatch {
  id: string;
  watch_type: string;
  origin: string | null;
  destination: string | null;
  target_date: string;
  flexibility_days: number;
  target_price: number | null;
  current_best_price: number | null;
  cabin_class: string;
  is_active: boolean;
  last_checked_at: string | null;
  alert_count: number;
  created_at: string | null;
  trend: "up" | "down" | "flat";
  price_history: PriceHistoryPoint[];
}

export interface PriceHistoryPoint {
  price: number;
  checked_at: string;
}

export interface Alert {
  id: string;
  type: "price_drop" | "booking_reminder" | "event_warning";
  title: string;
  body: string;
  is_read: boolean;
  reference_type: string | null;
  reference_id: string | null;
  created_at: string | null;
}
