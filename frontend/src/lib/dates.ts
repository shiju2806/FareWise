/**
 * Format a date string as a short human-readable date.
 *
 * Examples:
 *   formatShortDate("2026-03-15")       → "Sun, Mar 15"
 *   formatShortDate("2026-03-15T09:00") → "Sun, Mar 15"
 */
export function formatShortDate(dateStr: string): string {
  if (!dateStr) return "";
  const iso = dateStr.length === 10 ? dateStr + "T00:00:00" : dateStr;
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    weekday: "short",
  });
}
