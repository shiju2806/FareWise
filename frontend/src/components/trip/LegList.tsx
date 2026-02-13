import type { TripLeg } from "@/types/trip";
import { LegCard } from "./LegCard";

interface Props {
  legs: TripLeg[];
  editable?: boolean;
  onRemove?: (index: number) => void;
}

export function LegList({ legs, editable = false, onRemove }: Props) {
  if (legs.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground text-sm">
        No legs added yet. Use the form above to add trip legs.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-muted-foreground">
        Trip legs ({legs.length})
      </h3>
      {legs.map((leg, i) => (
        <LegCard
          key={leg.id || i}
          leg={leg}
          index={i}
          editable={editable}
          onRemove={onRemove}
        />
      ))}
    </div>
  );
}
