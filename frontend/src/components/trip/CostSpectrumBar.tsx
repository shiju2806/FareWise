/**
 * Cost spectrum bar — visualizes cheapest/selected/expensive price positions.
 * Shared between TripReview and ApprovalDetailPage.
 */

import { formatPrice } from "@/lib/currency";

interface CostSpectrumBarProps {
  cheapest: number;
  selected: number;
  mostExpensive: number;
  currency?: string;
}

export function CostSpectrumBar({ cheapest, selected, mostExpensive, currency }: CostSpectrumBarProps) {
  const max = mostExpensive || 1; // Avoid division by zero

  return (
    <div className="space-y-1">
      <div className="relative h-6 bg-muted rounded-full overflow-visible">
        {/* Green zone: 0 → cheapest */}
        <div
          className="absolute h-full bg-green-200 rounded-l-full"
          style={{ width: `${(cheapest / max) * 100}%` }}
        />
        {/* Amber zone: cheapest → selected */}
        {selected > cheapest && (
          <div
            className="absolute h-full bg-amber-200"
            style={{
              left: `${(cheapest / max) * 100}%`,
              width: `${((selected - cheapest) / max) * 100}%`,
            }}
          />
        )}
        {/* Selected price indicator */}
        <div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-5 h-5 rounded-full bg-primary border-2 border-white shadow-md z-10"
          style={{ left: `${(selected / max) * 100}%` }}
        />
      </div>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>Cheapest: {formatPrice(cheapest, currency)}</span>
        <span className="font-medium text-foreground">Selected: {formatPrice(selected, currency)}</span>
        <span>Expensive: {formatPrice(mostExpensive, currency)}</span>
      </div>
    </div>
  );
}
