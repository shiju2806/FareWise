import type { FlightOption } from "@/types/flight";
import { formatPrice } from "@/lib/currency";
import { formatShortDate } from "@/lib/dates";

interface Props {
  flight: FlightOption;
  isRecommended?: boolean;
  reason?: string;
  onSelect?: (flight: FlightOption) => void;
  /** Price quartile thresholds for color-coding [q1, q3] */
  priceQuartiles?: { q1: number; q3: number };
  /** Preferred date for the leg (used for date badge styling) */
  preferredDate?: string;
  /** Show departure date badge (used in all-dates view) */
  showDate?: boolean;
}

/** Hash a short string into a hue (0-360) for deterministic airline colors */
function airlineHue(code: string): number {
  let hash = 0;
  for (let i = 0; i < code.length; i++) {
    hash = code.charCodeAt(i) + ((hash << 5) - hash);
  }
  return Math.abs(hash) % 360;
}

function formatTime(iso: string): string {
  if (!iso) return "--:--";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h${m.toString().padStart(2, "0")}m`;
}

/** Returns +1 / +2 if arrival is on a later calendar day than departure */
function dayOffset(departure: string, arrival: string): number | null {
  if (!departure || !arrival) return null;
  const dep = new Date(departure);
  const arr = new Date(arrival);
  const depDay = new Date(dep.getFullYear(), dep.getMonth(), dep.getDate());
  const arrDay = new Date(arr.getFullYear(), arr.getMonth(), arr.getDate());
  const diff = Math.round(
    (arrDay.getTime() - depDay.getTime()) / (1000 * 60 * 60 * 24),
  );
  return diff > 0 ? diff : null;
}

function priceBadgeColor(price: number, q?: { q1: number; q3: number }): string {
  if (!q || q.q1 === 0) return "bg-emerald-50 text-emerald-700";
  if (price <= q.q1) return "bg-emerald-50 text-emerald-700";
  if (price >= q.q3) return "bg-red-50 text-red-700";
  return "bg-amber-50 text-amber-700";
}

export function FlightOptionCard({
  flight,
  isRecommended,
  reason,
  onSelect,
  priceQuartiles,
  preferredDate,
  showDate,
}: Props) {
  const hue = airlineHue(flight.airline_code);
  const overnight = dayOffset(flight.departure_time, flight.arrival_time);

  const stopsLabel =
    flight.stops === 0
      ? "Nonstop"
      : `${flight.stops} stop${flight.stops > 1 ? "s" : ""}`;

  return (
    <div
      className={[
        "group relative rounded-md border transition-all",
        "hover:shadow-md hover:-translate-y-px",
        isRecommended
          ? "border-l-[3px] border-l-primary border-y-primary/30 border-r-primary/30 bg-primary/[0.03]"
          : "border-border bg-card",
        onSelect ? "cursor-pointer" : "",
      ].join(" ")}
      onClick={() => onSelect?.(flight)}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={(e) => {
        if (onSelect && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onSelect(flight);
        }
      }}
    >
      {/* Main row */}
      <div className="flex items-center gap-3 px-3 py-2 min-h-[52px]">
        {/* ---- Airline ---- */}
        <div className="flex items-center gap-2 w-[160px] shrink-0">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0"
            style={{ backgroundColor: `hsl(${hue}, 55%, 48%)` }}
          >
            {flight.airline_code.slice(0, 2)}
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium leading-tight truncate">
              {flight.airline_name}
            </div>
            <div className="text-[10px] text-muted-foreground leading-tight truncate">
              {flight.flight_numbers}
            </div>
          </div>
        </div>

        {/* ---- Times + Route ---- */}
        <div className="flex items-center gap-1.5 flex-1 min-w-0">
          {/* Departure */}
          <div className="text-right shrink-0">
            <div className="text-sm font-semibold leading-tight">
              {formatTime(flight.departure_time)}
            </div>
            <div className="text-[10px] text-muted-foreground leading-tight">
              {flight.origin_airport}
            </div>
          </div>

          {/* Arrow connector */}
          <div className="flex items-center gap-0.5 px-1 shrink-0">
            <div className="w-4 h-px bg-border" />
            <svg
              className="w-2.5 h-2.5 text-muted-foreground"
              viewBox="0 0 10 10"
              fill="none"
            >
              <path
                d="M2 5h6M6 3l2 2-2 2"
                stroke="currentColor"
                strokeWidth="1.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <div className="w-4 h-px bg-border" />
          </div>

          {/* Arrival */}
          <div className="shrink-0">
            <div className="text-sm font-semibold leading-tight">
              {formatTime(flight.arrival_time)}
              {overnight && (
                <sup className="text-[9px] text-orange-500 font-semibold ml-0.5">
                  +{overnight}
                </sup>
              )}
            </div>
            <div className="text-[10px] text-muted-foreground leading-tight">
              {flight.destination_airport}
            </div>
          </div>
        </div>

        {/* ---- Duration + Stops ---- */}
        <div className="w-[120px] shrink-0 text-center">
          <div className="text-xs text-foreground leading-tight">
            {formatDuration(flight.duration_minutes)}
            <span className="mx-1 text-muted-foreground">·</span>
            <span
              className={
                flight.stops === 0
                  ? "text-emerald-600 font-medium"
                  : flight.duration_minutes > 720
                  ? "text-amber-600 font-medium"
                  : "text-muted-foreground"
              }
            >
              {stopsLabel}
            </span>
          </div>
          {flight.stop_airports && (
            <div className="text-[10px] text-muted-foreground leading-tight truncate">
              via {flight.stop_airports}
            </div>
          )}
          {flight.stops > 0 && flight.duration_minutes > 720 && (
            <div className="text-[9px] text-amber-600 font-medium leading-tight">
              Long layover
            </div>
          )}
        </div>

        {/* ---- Badges ---- */}
        <div className="flex items-center gap-1 shrink-0 flex-wrap max-w-[140px]">
          {isRecommended && (
            <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-primary/10 text-primary whitespace-nowrap">
              Recommended
            </span>
          )}
          {flight.stops === 0 && !isRecommended && (
            <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 whitespace-nowrap">
              Nonstop
            </span>
          )}
          {flight.is_alternate_airport && (
            <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-blue-50 text-blue-700 whitespace-nowrap">
              Alt Airport
            </span>
          )}
          {flight.is_alternate_date && !showDate && (
            <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-purple-50 text-purple-700 whitespace-nowrap">
              Flex Date
            </span>
          )}
          {showDate && flight.departure_time && (
            <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded-full whitespace-nowrap ${
              flight.departure_time.startsWith(preferredDate || "")
                ? "bg-primary/10 text-primary"
                : "bg-purple-50 text-purple-700"
            }`}>
              {formatShortDate(flight.departure_time)}
            </span>
          )}
          {flight.stops > 0 && flight.duration_minutes > 720 && (
            <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-700 whitespace-nowrap">
              {formatDuration(flight.duration_minutes)} total
            </span>
          )}
          {flight.seats_remaining != null && flight.seats_remaining <= 5 && (
            <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-red-50 text-red-700 whitespace-nowrap">
              {flight.seats_remaining} left
            </span>
          )}
        </div>

        {/* ---- Price ---- */}
        <div className="w-[80px] shrink-0 flex flex-col items-end gap-0.5">
          <span className={`inline-flex items-center text-sm font-bold px-2.5 py-0.5 rounded-full ${priceBadgeColor(flight.price, priceQuartiles)}`}>
            {formatPrice(flight.price, flight.currency)}
          </span>
          {flight.cabin_class && (
            <span className="text-[10px] text-muted-foreground capitalize leading-tight">
              {flight.cabin_class}
            </span>
          )}
        </div>

        {/* ---- Select Button ---- */}
        {onSelect && (
          <button
            type="button"
            className="shrink-0 text-xs font-medium px-3 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              onSelect(flight);
            }}
          >
            Select
          </button>
        )}
      </div>

      {/* Reason line (only when recommended) */}
      {isRecommended && reason && (
        <div className="px-3 pb-2 -mt-0.5">
          <p className="text-[11px] text-primary/80 leading-snug">{reason}</p>
        </div>
      )}
    </div>
  );
}
