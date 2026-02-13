import type { TripLeg } from "@/types/trip";

interface Props {
  leg: TripLeg;
  index: number;
  onRemove?: (index: number) => void;
  editable?: boolean;
}

export function LegCard({ leg, index, onRemove, editable = false }: Props) {
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
        <div className="flex gap-4 mt-1 text-xs text-muted-foreground">
          <span>{leg.preferred_date}</span>
          <span className="capitalize">{leg.cabin_class}</span>
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
