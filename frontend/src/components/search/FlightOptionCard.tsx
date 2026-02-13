import type { FlightOption } from "@/types/flight";

interface Props {
  flight: FlightOption;
  isRecommended?: boolean;
  reason?: string;
  onSelect?: (flight: FlightOption) => void;
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
  return `${h}h ${m}m`;
}

export function FlightOptionCard({
  flight,
  isRecommended,
  reason,
  onSelect,
}: Props) {
  return (
    <div
      className={`
        rounded-lg border p-4 transition-all hover:shadow-md
        ${isRecommended ? "border-primary bg-primary/5 ring-1 ring-primary/20" : "border-border bg-card"}
        ${onSelect ? "cursor-pointer" : ""}
      `}
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
      {isRecommended && reason && (
        <div className="text-xs text-primary font-medium mb-2">{reason}</div>
      )}

      <div className="flex items-center gap-4">
        {/* Airline */}
        <div className="w-20 shrink-0">
          <div className="text-sm font-semibold">{flight.airline_code}</div>
          <div className="text-[10px] text-muted-foreground truncate">
            {flight.airline_name}
          </div>
          <div className="text-[10px] text-muted-foreground">
            {flight.flight_numbers}
          </div>
        </div>

        {/* Times + Route */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <div className="text-right">
              <div className="text-sm font-semibold">
                {formatTime(flight.departure_time)}
              </div>
              <div className="text-[10px] text-muted-foreground">
                {flight.origin_airport}
              </div>
            </div>

            <div className="flex-1 flex flex-col items-center px-2">
              <div className="text-[10px] text-muted-foreground">
                {formatDuration(flight.duration_minutes)}
              </div>
              <div className="w-full flex items-center gap-1">
                <div className="h-px flex-1 bg-border" />
                {flight.stops === 0 ? (
                  <span className="text-[10px] text-emerald-600 font-medium">
                    Nonstop
                  </span>
                ) : (
                  <span className="text-[10px] text-muted-foreground">
                    {flight.stops} stop{flight.stops > 1 ? "s" : ""}
                  </span>
                )}
                <div className="h-px flex-1 bg-border" />
              </div>
              {flight.stop_airports && (
                <div className="text-[10px] text-muted-foreground">
                  via {flight.stop_airports}
                </div>
              )}
            </div>

            <div>
              <div className="text-sm font-semibold">
                {formatTime(flight.arrival_time)}
              </div>
              <div className="text-[10px] text-muted-foreground">
                {flight.destination_airport}
              </div>
            </div>
          </div>
        </div>

        {/* Price + badges */}
        <div className="text-right shrink-0 w-24">
          <div className="text-lg font-bold">
            ${Math.round(flight.price)}
          </div>
          <div className="text-[10px] text-muted-foreground capitalize">
            {flight.cabin_class}
          </div>
          <div className="flex justify-end gap-1 mt-1">
            {flight.is_alternate_airport && (
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">
                Alt airport
              </span>
            )}
            {flight.is_alternate_date && (
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-100 text-purple-700">
                Flex date
              </span>
            )}
            {flight.seats_remaining !== null &&
              flight.seats_remaining !== undefined &&
              flight.seats_remaining <= 5 && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-100 text-red-700">
                  {flight.seats_remaining} left
                </span>
              )}
          </div>
          {flight.score !== undefined && (
            <div className="text-[10px] text-muted-foreground mt-1">
              Score: {flight.score}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
