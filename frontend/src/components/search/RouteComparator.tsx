import { useState } from "react";
import type { FlightOption } from "@/types/flight";
import { FlightOptionCard } from "./FlightOptionCard";

interface Props {
  alternatives: {
    cheaper_dates: FlightOption[];
    alternate_airports: FlightOption[];
    different_routing: FlightOption[];
  };
  onSelect?: (flight: FlightOption) => void;
}

const SECTIONS = [
  { key: "cheaper_dates" as const, label: "Cheaper Dates", description: "Save by shifting your travel date" },
  { key: "alternate_airports" as const, label: "Alternate Airports", description: "Nearby airports with better prices" },
  { key: "different_routing" as const, label: "Different Routing", description: "Connecting flights that save money" },
];

export function RouteComparator({ alternatives, onSelect }: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    cheaper_dates: true,
    alternate_airports: true,
    different_routing: false,
  });

  const toggle = (key: string) =>
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));

  const hasAny =
    alternatives.cheaper_dates.length > 0 ||
    alternatives.alternate_airports.length > 0 ||
    alternatives.different_routing.length > 0;

  if (!hasAny) {
    return null;
  }

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold">Alternatives</h3>

      {SECTIONS.map(({ key, label, description }) => {
        const items = alternatives[key];
        if (items.length === 0) return null;

        return (
          <div key={key} className="rounded-lg border border-border">
            <button
              type="button"
              onClick={() => toggle(key)}
              className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-accent/50 transition-colors"
            >
              <div>
                <span className="text-sm font-medium">{label}</span>
                <span className="text-xs text-muted-foreground ml-2">
                  ({items.length})
                </span>
                <p className="text-xs text-muted-foreground">{description}</p>
              </div>
              <span className="text-muted-foreground text-sm">
                {expanded[key] ? "\u25B2" : "\u25BC"}
              </span>
            </button>

            {expanded[key] && (
              <div className="px-4 pb-3 space-y-2">
                {items.map((flight, i) => (
                  <FlightOptionCard
                    key={flight.id || i}
                    flight={flight}
                    onSelect={onSelect}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
