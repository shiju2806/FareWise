import { useMemo } from "react";
import type { FlightOption } from "@/types/flight";

interface Props {
  allOptions: FlightOption[];
  datesSearched: string[];
  excludedAirlines?: string[];
  onFlightSelect?: (flight: FlightOption) => void;
}

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function fmtDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  const mon = d.toLocaleString("en-US", { month: "short" });
  return `${mon} ${d.getDate()} ${DAY_NAMES[d.getDay()]}`;
}

function fmtPrice(price: number): string {
  if (price >= 1000) {
    const k = price / 1000;
    return `$${k % 1 === 0 ? k.toFixed(0) : k.toFixed(1)}k`;
  }
  return `$${Math.round(price)}`;
}

export function AirlineDateMatrix({
  allOptions,
  datesSearched,
  excludedAirlines = [],
  onFlightSelect,
}: Props) {
  const excludedSet = useMemo(() => new Set(excludedAirlines), [excludedAirlines]);

  const { airlines, dates, cheapestByDate, q1, q3 } = useMemo(() => {
    // Group by airline → date → cheapest flight
    const airlineMap = new Map<string, Map<string, FlightOption>>();

    for (const f of allOptions) {
      const dateStr = f.departure_time.substring(0, 10);
      if (!airlineMap.has(f.airline_name)) {
        airlineMap.set(f.airline_name, new Map());
      }
      const dateMap = airlineMap.get(f.airline_name)!;
      if (!dateMap.has(dateStr) || f.price < dateMap.get(dateStr)!.price) {
        dateMap.set(dateStr, f);
      }
    }

    // Sort airlines by cheapest overall
    const airlines = Array.from(airlineMap.entries())
      .map(([name, dateMap]) => ({
        name,
        dateMap,
        minPrice: Math.min(...Array.from(dateMap.values()).map((f) => f.price)),
        excluded: excludedSet.has(name),
      }))
      .sort((a, b) => {
        // Non-excluded first, then by price
        if (a.excluded !== b.excluded) return a.excluded ? 1 : -1;
        return a.minPrice - b.minPrice;
      });

    // Sorted dates
    const dates = [...datesSearched].sort();

    // Cheapest per date (among non-excluded airlines only)
    const cheapestByDate = new Map<string, number>();
    for (const d of dates) {
      const dayPrices = allOptions
        .filter(
          (f) =>
            f.departure_time.startsWith(d) && !excludedSet.has(f.airline_name)
        )
        .map((f) => f.price);
      if (dayPrices.length > 0) cheapestByDate.set(d, Math.min(...dayPrices));
    }

    // Quartiles for color coding (non-excluded only)
    const allPrices = allOptions
      .filter((f) => !excludedSet.has(f.airline_name))
      .map((f) => f.price)
      .sort((a, b) => a - b);
    const q1 =
      allPrices.length > 0
        ? allPrices[Math.floor(allPrices.length * 0.25)]
        : 0;
    const q3 =
      allPrices.length > 0
        ? allPrices[Math.floor(allPrices.length * 0.75)]
        : 0;

    return { airlines, dates, cheapestByDate, q1, q3 };
  }, [allOptions, datesSearched, excludedSet]);

  if (airlines.length === 0 || dates.length === 0) return null;

  function cellColor(price: number, excluded: boolean): string {
    if (excluded) return "bg-muted/30 text-muted-foreground/50";
    if (price <= q1) return "bg-emerald-50 text-emerald-700";
    if (price >= q3) return "bg-red-50 text-red-700";
    return "bg-amber-50 text-amber-700";
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">Price Matrix — Airlines × Dates</h3>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="text-[11px] w-full border-collapse">
          <thead>
            <tr className="bg-muted/50">
              <th className="sticky left-0 z-10 bg-muted/50 text-left px-2 py-1.5 font-semibold min-w-[120px] border-r border-border">
                Airline
              </th>
              {dates.map((d) => (
                <th
                  key={d}
                  className="px-1.5 py-1.5 font-medium text-center whitespace-nowrap min-w-[68px]"
                >
                  {fmtDate(d)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {airlines.map((airline) => {
              const isRowCheapest = (d: string, price: number) =>
                price === airline.minPrice;
              const isColCheapest = (d: string, price: number) =>
                cheapestByDate.get(d) === price && !airline.excluded;

              return (
                <tr
                  key={airline.name}
                  className={`border-t border-border/50 ${
                    airline.excluded ? "opacity-40" : ""
                  }`}
                >
                  <td
                    className={`sticky left-0 z-10 px-2 py-1.5 border-r border-border ${
                      airline.excluded
                        ? "bg-muted/20 line-through"
                        : "bg-card"
                    }`}
                  >
                    <div className="font-semibold truncate max-w-[110px]">
                      {airline.name}
                    </div>
                    <div className="text-[9px] text-muted-foreground">
                      from {fmtPrice(airline.minPrice)}
                    </div>
                  </td>
                  {dates.map((d) => {
                    const flight = airline.dateMap.get(d);
                    if (!flight) {
                      return (
                        <td
                          key={d}
                          className="px-1.5 py-1.5 text-center text-muted-foreground/40"
                        >
                          —
                        </td>
                      );
                    }

                    const price = flight.price;
                    const rowBest = isRowCheapest(d, price);
                    const colBest = isColCheapest(d, price);

                    return (
                      <td key={d} className="px-0.5 py-0.5">
                        <button
                          type="button"
                          onClick={() =>
                            !airline.excluded && onFlightSelect?.(flight)
                          }
                          disabled={airline.excluded}
                          className={`w-full rounded px-1 py-1 text-center transition-all ${cellColor(price, airline.excluded)} ${
                            airline.excluded
                              ? "cursor-not-allowed"
                              : "cursor-pointer hover:ring-1 hover:ring-primary/40 hover:shadow-sm"
                          } ${
                            rowBest && colBest && !airline.excluded
                              ? "ring-2 ring-emerald-500 font-bold"
                              : rowBest && !airline.excluded
                              ? "font-bold"
                              : ""
                          }`}
                          title={
                            airline.excluded
                              ? `${airline.name} — excluded`
                              : `${airline.name} · ${flight.stops === 0 ? "Nonstop" : `${flight.stops} stop${flight.stops > 1 ? "s" : ""}`} · ${flight.duration_minutes}min`
                          }
                        >
                          <span className="text-[11px]">
                            {fmtPrice(price)}
                          </span>
                          {(rowBest || colBest) && !airline.excluded && (
                            <span className="ml-0.5 text-[8px]">
                              {rowBest && colBest
                                ? "\u2605"
                                : colBest
                                ? "\u25CF"
                                : ""}
                            </span>
                          )}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex gap-3 text-[9px] text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded bg-emerald-50 border border-emerald-300" />
          Cheap
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded bg-amber-50 border border-amber-300" />
          Mid
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded bg-red-50 border border-red-300" />
          Expensive
        </span>
        <span>
          <strong>Bold</strong> = cheapest for this airline
        </span>
        <span>{"\u2605"} = cheapest airline + date</span>
      </div>
    </div>
  );
}
