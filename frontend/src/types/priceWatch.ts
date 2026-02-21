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