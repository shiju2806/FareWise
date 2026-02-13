import type { TripOverlap } from "@/types/collaboration";

interface Props {
  overlaps: TripOverlap[];
  onDismiss: (overlapId: string) => void;
}

export function OverlapAlert({ overlaps, onDismiss }: Props) {
  const active = overlaps.filter((o) => !o.dismissed);
  if (active.length === 0) return null;

  return (
    <div className="rounded-md border border-blue-200 bg-blue-50 p-3 space-y-2">
      <p className="text-sm font-medium text-blue-800">
        Trip Overlap{active.length > 1 ? "s" : ""} Detected
      </p>
      {active.map((o) => (
        <div
          key={o.id}
          className="flex items-center justify-between text-sm text-blue-700"
        >
          <span>
            {o.other_trip.traveler}
            {o.other_trip.department ? ` (${o.other_trip.department})` : ""} is
            also in {o.overlap_city} {o.overlap_start} — {o.overlap_end} (
            {o.overlap_days} days)
          </span>
          <button
            type="button"
            onClick={() => onDismiss(o.id)}
            className="text-xs text-blue-500 hover:underline ml-2 flex-shrink-0"
          >
            Dismiss
          </button>
        </div>
      ))}
    </div>
  );
}
