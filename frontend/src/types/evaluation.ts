/**
 * Canonical types for trip evaluation, policy checks, and review analysis.
 * Single source of truth — used by TripReview, ApprovalDetailPage, and InlineReviewPanel.
 */

import type { TripWindowProposal } from "./search";

export interface PolicyCheck {
  policy_name: string;
  status: string;
  details: string;
  rule_type?: string;
  policy_id?: string;
  severity?: number;
}

export interface Warning {
  policy_name: string;
  message: string;
  action?: string;
  policy_id?: string;
  requires_justification?: boolean;
}

export interface Block {
  policy_name: string;
  message: string;
  policy_id: string;
}

export interface LegSummary {
  leg_id: string;
  route: string;
  selected_price: number;
  cheapest_price: number;
  most_expensive_price?: number;
  selected_airline?: string;
  justification_note?: string | null;
  savings_note?: string | null;
  policy_status?: string;
}

export interface ReviewAlternative {
  type: string;
  label: string;
  airline: string;
  date: string;
  price: number;
  savings: number;
  stops: number;
  flight_option_id: string;
}

export interface ReviewLeg {
  leg_id: string;
  sequence: number;
  route: string;
  selected: {
    airline: string;
    date: string;
    price: number;
    stops: number;
    flight_option_id: string;
  } | null;
  savings: { amount: number; percent: number };
  alternatives: ReviewAlternative[];
}

export interface ReviewAnalysis {
  legs: ReviewLeg[];
  trip_totals: {
    selected: number;
    cheapest: number;
    savings_amount: number;
    savings_percent: number;
  };
  trip_window_alternatives?: {
    original_trip_duration: number;
    original_total_price: number;
    proposals: TripWindowProposal[];
    different_month?: TripWindowProposal[];
  } | null;
}

export interface SavingsReport {
  currency?: string;
  selected_total: number;
  cheapest_total: number;
  most_expensive_total: number;
  savings_vs_expensive: number;
  premium_vs_cheapest: number;
  narrative: string;
  policy_status: string;
  policy_checks: PolicyCheck[];
  per_leg_summary: LegSummary[];
  hotel_selected_total?: number | null;
  hotel_cheapest_total?: number | null;
  events_context?: string[] | null;
  slider_positions?: Record<string, number | null>;
}

export interface EvalResult {
  savings_report: SavingsReport | null;
  warnings: Warning[];
  blocks: Block[];
  selected_flights?: Record<string, string>;
  analysis_snapshot?: {
    legs: ReviewLeg[];
    trip_totals: ReviewAnalysis["trip_totals"];
    trip_window_alternatives: ReviewAnalysis["trip_window_alternatives"];
    saved_at: string;
  } | null;
  error?: string;
}
