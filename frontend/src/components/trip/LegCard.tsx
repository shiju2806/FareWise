import { useState } from "react";
import type { TripLeg } from "@/types/trip";
import { useTripStore } from "@/stores/tripStore";
import { useSearchStore } from "@/stores/searchStore";
import { useToastStore } from "@/stores/toastStore";

interface Props {
  leg: TripLeg;
  index: number;
  onRemove?: (index: number) => void;
  editable?: boolean;
}

const CABIN_OPTIONS = ["economy", "premium_economy", "business", "first"];

export function LegCard({ leg, index, onRemove, editable = false }: Props) {
  const [cabinClass, setCabinClass] = useState(leg.cabin_class);
  const [passengers, setPassengers] = useState(leg.passengers);
  const [saving, setSaving] = useState(false);
  const patchLeg = useTripStore((s) => s.patchLeg);
  const searchLeg = useSearchStore((s) => s.searchLeg);
  const refreshLeg = useSearchStore((s) => s.refreshLeg);

  async function handleCabinChange(value: string) {
    if (value === cabinClass) return;
    const prev = cabinClass;
    setCabinClass(value);
    setSaving(true);
    try {
      await patchLeg(leg.id, { cabin_class: value });
      searchLeg(leg.id);
    } catch {
      setCabinClass(prev);
    } finally {
      setSaving(false);
    }
  }

  async function handlePassengersChange(value: number) {
    if (value === passengers) return;
    const prev = passengers;
    setPassengers(value);
    setSaving(true);
    try {
      // Determine if cabin needs to downgrade based on passenger policy
      let newCabin = cabinClass;
      if (value >= 4 && cabinClass !== "economy") {
        newCabin = "economy";
      } else if (value >= 2 && (cabinClass === "business" || cabinClass === "first")) {
        newCabin = "premium_economy";
      }

      // Patch passengers (and cabin if policy requires downgrade)
      const patch: Record<string, unknown> = { passengers: value };
      if (newCabin !== cabinClass) {
        patch.cabin_class = newCabin;
        setCabinClass(newCabin);
        useToastStore.getState().addToast(
          "info",
          `${value} passengers — cabin changed to ${newCabin.replace("_", " ")} per company policy.`
        );
      }
      await patchLeg(leg.id, patch);

      // Silent refresh: prices update in background without loading skeleton
      refreshLeg(leg.id);
    } catch {
      setPassengers(prev);
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
          <select
            value={passengers}
            onChange={(e) => handlePassengersChange(Number(e.target.value))}
            disabled={saving}
            className="bg-transparent border border-border rounded px-1.5 py-0.5 text-xs cursor-pointer hover:border-primary/50 transition-colors"
          >
            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
              <option key={n} value={n}>
                {n} {n === 1 ? "passenger" : "passengers"}
              </option>
            ))}
          </select>
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
