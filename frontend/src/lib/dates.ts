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

/**
 * Format flight duration in minutes to a compact string.
 *
 * Examples:
 *   formatDuration(125) → "2h05m"
 *   formatDuration(60)  → "1h00m"
 */
export function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h${m.toString().padStart(2, "0")}m`;
}
