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

/**
 * Compact price for space-constrained UI: $1.5k for >=1000, $843 for <1000.
 *
 * Examples:
 *   formatCompactPrice(1500) → "$1.5k"
 *   formatCompactPrice(2000) → "$2k"
 *   formatCompactPrice(843)  → "$843"
 */
export function formatCompactPrice(price: number): string {
  if (price >= 1000) {
    const k = price / 1000;
    return `$${k % 1 === 0 ? k.toFixed(0) : k.toFixed(1)}k`;
  }
  return `$${Math.round(price)}`;
}

/**
 * Simple price with locale formatting: $1,234.
 */
export function formatSimplePrice(price: number): string {
  return `$${Math.round(price).toLocaleString()}`;
}
