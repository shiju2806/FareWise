import { TripStatusBadge } from "./TripStatusBadge";

export interface CalendarTripData {
  id: string;
  title: string;
  status: string;
  start_date: string;
  end_date: string;
  legs: { id: string; origin: string; destination: string; date: string }[];
  total_estimated_cost: number | null;
  currency: string;
}

export type BarSegment = "start" | "middle" | "end" | "single";

const BAR_COLORS = [
  "bg-blue-500",
  "bg-teal-500",
  "bg-violet-500",
  "bg-amber-500",
  "bg-rose-500",
  "bg-emerald-500",
];

export function getBarColor(index: number): string {
  return BAR_COLORS[index % BAR_COLORS.length];
}

interface Props {
  trip: CalendarTripData;
  segment: BarSegment;
  colorClass: string;
  onClick: () => void;
}

export function TripBar({ trip, segment, colorClass, onClick }: Props) {
  const isDraft = trip.status === "draft";
  const isRejected = trip.status === "rejected";

  const roundingClass =
    segment === "start"
      ? "rounded-l-md"
      : segment === "end"
        ? "rounded-r-md"
        : segment === "single"
          ? "rounded-md"
          : "";

  const showLabel = segment === "start" || segment === "single";

  return (
    <div className="group relative">
      <button
        type="button"
        onClick={onClick}
        className={`
          w-full h-5 text-[10px] font-medium text-white
          flex items-center px-1.5 truncate cursor-pointer
          transition-all hover:brightness-110 hover:shadow-sm
          ${colorClass} ${roundingClass}
          ${isDraft ? "opacity-60" : ""}
          ${isRejected ? "opacity-40 line-through" : ""}
        `}
      >
        {showLabel && (
          <span className="truncate">{trip.title}</span>
        )}
      </button>

      {/* Tooltip on hover */}
      <div className="
        invisible group-hover:visible opacity-0 group-hover:opacity-100
        absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-1.5
        bg-popover text-popover-foreground border border-border
        rounded-lg shadow-lg p-2.5 min-w-[180px] max-w-[240px]
        pointer-events-none transition-opacity duration-150
      ">
        <p className="text-xs font-semibold truncate">{trip.title}</p>
        <div className="flex items-center gap-1.5 mt-1">
          <TripStatusBadge status={trip.status} />
          {trip.total_estimated_cost != null && (
            <span className="text-[10px] text-muted-foreground">
              {trip.currency} {trip.total_estimated_cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </span>
          )}
        </div>
        <p className="text-[10px] text-muted-foreground mt-1">
          {trip.start_date} &rarr; {trip.end_date}
        </p>
        {trip.legs.length > 0 && (
          <p className="text-[10px] text-muted-foreground">
            {trip.legs.map((l) => `${l.origin}-${l.destination}`).join(", ")}
          </p>
        )}
      </div>
    </div>
  );
}
