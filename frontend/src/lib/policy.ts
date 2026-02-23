/**
 * Policy status display constants — single source of truth.
 * Used by TripReview, ApprovalDetailPage, InlineReviewPanel, and FlightOptionCard.
 */

import type { PolicyCheck } from "../types/evaluation";
import type { FlightPolicyStatus } from "../types/search";

export const statusIcons: Record<string, string> = {
  pass: "\u2713",
  warn: "\u26A0",
  block: "\u2715",
  info: "\u2139",
};

export const statusColors: Record<string, string> = {
  pass: "text-green-600",
  warn: "text-amber-600",
  block: "text-red-600",
  info: "text-blue-600",
};

const STATUS_SEVERITY: Record<string, number> = {
  block: 3, warn: 2, info: 1, pass: 0,
};

const STATUS_LABELS: Record<string, string> = {
  pass: "Policy compliant",
  info: "Policy note",
  warn: "Policy warning",
  block: "Policy violation",
};

export const policyBadgeColors: Record<string, string> = {
  pass: "bg-green-50 text-green-700 border-green-200",
  info: "bg-blue-50 text-blue-700 border-blue-200",
  warn: "bg-amber-50 text-amber-700 border-amber-200",
  block: "bg-red-50 text-red-700 border-red-200",
};

export function getFlightPolicyStatus(
  checks: PolicyCheck[] | undefined
): FlightPolicyStatus | null {
  if (!checks || checks.length === 0) return null;
  const worst = checks.reduce(
    (w, c) => ((STATUS_SEVERITY[c.status] ?? 0) > (STATUS_SEVERITY[w] ?? 0) ? c.status : w),
    "pass"
  ) as FlightPolicyStatus["worst"];
  return { worst, checks, label: STATUS_LABELS[worst] ?? "Policy check" };
}
