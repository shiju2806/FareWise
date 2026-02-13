import { useState } from "react";
import type { TripLeg } from "@/types/trip";
import apiClient from "@/api/client";

interface Props {
  leg: TripLeg;
  index: number;
  onRemove?: (index: number) => void;
  editable?: boolean;
}

const CABIN_OPTIONS = ["economy", "premium_economy", "business", "first"];

export function LegCard({ leg, index, onRemove, editable = false }: Props) {
  const [cabinClass, setCabinClass] = useState(leg.cabin_class);
  const [saving, setSaving] = useState(false);

  async function handleCabinChange(value: string) {
    setCabinClass(value);
    setSaving(true);
    try {
      await apiClient.patch(`/trips/legs/${leg.id}`, { cabin_class: value });
    } catch {
      setCabinClass(leg.cabin_class); // revert on error
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex items-center gap-4 rounded-lg border border-border p-4 bg-card">
      <div className="flex items-center justify-center w-8 h-8 rounded-full bg-primary/10 text-primary text-sm font-semibold shrink-0">
        {index + 1}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-sm font-medium">
          <span className="truncate">
            {leg.origin_city}
            {leg.origin_airport && (
              <span className="text-muted-foreground ml-1">
                ({leg.origin_airport})
              </span>
            )}
          </span>
          <span className="text-muted-foreground shrink-0">&rarr;</span>
          <span className="truncate">
            {leg.destination_city}
            {leg.destination_airport && (
              <span className="text-muted-foreground ml-1">
                ({leg.destination_airport})
              </span>
            )}
          </span>
        </div>
        <div className="flex gap-4 mt-1 text-xs text-muted-foreground items-center">
          <span>{leg.preferred_date}</span>
          <select
            value={cabinClass}
            onChange={(e) => handleCabinChange(e.target.value)}
            disabled={saving}
            className="bg-transparent border border-border rounded px-1.5 py-0.5 text-xs capitalize cursor-pointer hover:border-primary/50 transition-colors"
          >
            {CABIN_OPTIONS.map((opt) => (
              <option key={opt} value={opt} className="capitalize">
                {opt.replace("_", " ")}
              </option>
            ))}
          </select>
          <span>
            {leg.passengers} {leg.passengers === 1 ? "passenger" : "passengers"}
          </span>
          <span>&plusmn;{leg.flexibility_days}d flex</span>
        </div>
      </div>

      {editable && onRemove && (
        <button
          type="button"
          onClick={() => onRemove(index)}
          className="text-muted-foreground hover:text-destructive transition-colors text-sm shrink-0"
          aria-label={`Remove leg ${index + 1}`}
        >
          &times;
        </button>
      )}
    </div>
  );
}
