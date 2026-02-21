/**
 * Policy status display constants — single source of truth.
 * Used by TripReview, ApprovalDetailPage, and InlineReviewPanel.
 */

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
