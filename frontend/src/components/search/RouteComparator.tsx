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
  { key: "alternate_airports" as const, label: "Nearby Airports", description: "Same destination, lower prices" },
  { key: "different_routing" as const, label: "Connecting Flights", description: "One stop, bigger savings" },
];

const PREVIEW_COUNT = 3;

export function RouteComparator({ alternatives, onSelect }: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    cheaper_dates: false,
    alternate_airports: false,
    different_routing: false,
  });
  const [showAll, setShowAll] = useState<Record<string, boolean>>({});

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
    <div className="space-y-3">
      <h3 className="text-sm font-semibold">Alternatives</h3>

      {SECTIONS.map(({ key, label, description }) => {
        const items = alternatives[key];
        if (items.length === 0) return null;

        const isExpanded = expanded[key];
        const isShowAll = showAll[key];
        const displayItems = isShowAll ? items : items.slice(0, PREVIEW_COUNT);
        const hasMore = items.length > PREVIEW_COUNT;

        // Best price in this category
        const bestPrice = Math.min(...items.map((f) => f.price));

        return (
          <div key={key} className="rounded-lg border border-border">
            <button
              type="button"
              onClick={() => toggle(key)}
              className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-accent/50 transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">{label}</span>
                <span className="text-xs text-muted-foreground">
                  {items.length} option{items.length !== 1 ? "s" : ""}
                </span>
                <span className="text-xs font-medium text-green-600">
                  from ${Math.round(bestPrice)}
                </span>
              </div>
              <span className="text-muted-foreground text-xs">
                {isExpanded ? "\u25B2" : "\u25BC"}
              </span>
            </button>

            {isExpanded && (
              <div className="px-4 pb-3 space-y-2">
                {displayItems.map((flight, i) => (
                  <FlightOptionCard
                    key={flight.id || i}
                    flight={flight}
                    onSelect={onSelect}
                  />
                ))}
                {hasMore && !isShowAll && (
                  <button
                    type="button"
                    onClick={() => setShowAll((prev) => ({ ...prev, [key]: true }))}
                    className="text-xs text-primary hover:underline w-full text-center py-1"
                  >
                    Show all {items.length} options
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
