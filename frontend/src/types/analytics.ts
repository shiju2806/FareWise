export interface HeadlineMetrics {
  total_trips: number;
  total_spend: number;
  total_savings: number;
  active_users: number;
  compliance_rate: number;
}

export interface SpendTrendPoint {
  period_start: string;
  period_end: string;
  spend: number;
  trips: number;
}

export interface AnalyticsOverview {
  headline: HeadlineMetrics;
  spend_trend: SpendTrendPoint[];
  latest_snapshot: Record<string, unknown> | null;
}

export interface DepartmentAnalytics {
  department: string;
  users: number;
  trips: number;
  spend: number;
  savings: number;
  top_travelers: {
    name: string;
    score: number;
    trips: number;
    savings: number;
  }[];
}

export interface RouteAnalytics {
  origin: string;
  destination: string;
  total_bookings: number;
  avg_slider_position: number;
}

export interface SavingsSummary {
  total_reports: number;
  total_selected: number;
  total_cheapest: number;
  total_most_expensive: number;
  total_savings: number;
  avg_savings: number;
}

export interface LeaderboardEntry {
  user_id: string;
  name: string;
  department: string;
  score: number;
  tier: string;
  trips: number;
  savings: number;
  compliance: number;
  badges: string[];
  rank_company: number;
  rank_department: number;
}

export interface LeaderboardData {
  period: string;
  department: string | null;
  entries: LeaderboardEntry[];
}

export interface BadgeDetail {
  id: string;
  name: string;
  desc: string;
  icon: string;
  earned?: boolean;
}

export interface SavingsGoal {
  quarter: string;
  total_savings: number;
  target: number;
  trip_count: number;
  progress_pct: number;
}

export interface MyStats {
  current: {
    score: number;
    tier: string;
    streak: number;
    rank_department: number | null;
    rank_company: number | null;
    total_trips: number;
    total_spend: number;
    total_savings: number;
    compliance_rate: number;
    avg_advance_days: number;
    avg_slider: number;
  };
  badges: BadgeDetail[];
  all_badges: BadgeDetail[];
  history: {
    period: string;
    score: number;
    trips: number;
    savings: number;
    compliance: number;
  }[];
}
