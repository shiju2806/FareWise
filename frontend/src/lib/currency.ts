/**
 * Format a price with the correct currency symbol using Intl.NumberFormat.
 *
 * Examples:
 *   formatPrice(3412, "CAD") → "CA$3,412"
 *   formatPrice(2100, "GBP") → "£2,100"
 *   formatPrice(1500, "USD") → "$1,500"
 *   formatPrice(1200, "EUR") → "€1,200"
 */
export function formatPrice(
  amount: number,
  currency: string = "USD",
): string {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
      minimumFractionDigits: 0,
    }).format(Math.round(amount));
  } catch {
    // Fallback for unknown currency codes
    return `${currency} ${Math.round(amount).toLocaleString()}`;
  }
}
