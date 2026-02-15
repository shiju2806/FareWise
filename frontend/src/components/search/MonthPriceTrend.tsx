import { useEffect, useState } from "react";
import apiClient from "@/api/client";
import type { MonthCalendarData } from "@/types/search";

interface Props {
  legId: string;
  preferredDate: string;
}

interface MonthSummary {
  year: number;
  month: number;
  label: string;
  avgPrice: number;
  cheapestPrice: number;
  cheapestDate: string | null;
  datesWithFlights: number;
  datesWithDirect: number;
}

function fmtPrice(n: number): string {
  return `$${Math.round(n).toLocaleString()}`;
}

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function MonthPriceTrend({ legId, preferredDate }: Props) {
  const [months, setMonths] = useState<MonthSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchMonths() {
      setLoading(true);
      const preferred = new Date(preferredDate + "T00:00:00");
      const baseMonth = preferred.getMonth(); // 0-indexed
      const baseYear = preferred.getFullYear();

      // Fetch current month + next 2 months
      const monthsToFetch: { year: number; month: number }[] = [];
      for (let offset = 0; offset < 3; offset++) {
        let m = baseMonth + offset;
        let y = baseYear;
        if (m > 11) {
          m -= 12;
          y++;
        }
        monthsToFetch.push({ year: y, month: m + 1 }); // API uses 1-indexed
      }

      const results: MonthSummary[] = [];
      for (const { year, month } of monthsToFetch) {
        try {
          const res = await apiClient.get(`/search/${legId}/calendar`, {
            params: { year, month },
            timeout: 15000,
          });
          const data = res.data as MonthCalendarData;
          if (data.month_stats) {
            results.push({
              year,
              month,
              label: `${MONTH_NAMES[month - 1]} ${year}`,
              avgPrice: data.month_stats.avg_price,
              cheapestPrice: data.month_stats.cheapest_price,
              cheapestDate: data.month_stats.cheapest_date,
              datesWithFlights: data.month_stats.dates_with_flights,
              datesWithDirect: data.month_stats.dates_with_direct,
            });
          }
        } catch {
          // Skip months that fail
        }
      }

      if (!cancelled) {
        setMonths(results);
        setLoading(false);
      }
    }

    fetchMonths();
    return () => { cancelled = true; };
  }, [legId, preferredDate]);

  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-card p-3 animate-pulse">
        <div className="h-3 w-32 bg-muted rounded mb-2" />
        <div className="flex gap-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex-1 h-16 bg-muted/50 rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (months.length < 2) return null;

  const cheapestMonth = months.reduce((best, m) =>
    m.cheapestPrice < best.cheapestPrice ? m : best
  );
  const preferredMonth = months[0]; // First month is the preferred one
  const savings = preferredMonth && cheapestMonth && cheapestMonth !== preferredMonth
    ? preferredMonth.cheapestPrice - cheapestMonth.cheapestPrice
    : 0;

  // Find the max avg price for bar scaling
  const maxAvg = Math.max(...months.map((m) => m.avgPrice));

  return (
    <div className="rounded-lg border border-border bg-card shadow-sm">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2 flex items-center justify-between hover:bg-muted/20 transition-colors"
      >
        <div className="flex items-center gap-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Month Price Comparison
          </h4>
          {savings > 50 && (
            <span className="text-[10px] font-medium text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded">
              Save {fmtPrice(savings)} in {cheapestMonth.label}
            </span>
          )}
        </div>
        <span className="text-[10px] text-muted-foreground">
          {expanded ? "Hide" : "Show"}
        </span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 pt-1">
          <div className="flex gap-2">
            {months.map((m) => {
              const isCheapest = m === cheapestMonth;
              const isPreferred = m === preferredMonth;
              const barHeight = maxAvg > 0 ? Math.max(20, (m.avgPrice / maxAvg) * 60) : 40;

              return (
                <div
                  key={m.label}
                  className={`flex-1 rounded-lg border p-2 text-center transition-colors ${
                    isCheapest
                      ? "border-emerald-300 bg-emerald-50/60"
                      : isPreferred
                      ? "border-primary/30 bg-primary/5"
                      : "border-border bg-muted/10"
                  }`}
                >
                  <div className="text-[10px] font-semibold text-muted-foreground mb-1">
                    {m.label}
                    {isPreferred && !isCheapest && (
                      <span className="ml-1 text-primary">(your trip)</span>
                    )}
                    {isCheapest && (
                      <span className="ml-1 text-emerald-600">(cheapest)</span>
                    )}
                  </div>

                  {/* Mini bar chart */}
                  <div className="flex justify-center mb-1">
                    <div
                      className={`w-8 rounded-t transition-all ${
                        isCheapest ? "bg-emerald-400" : "bg-primary/30"
                      }`}
                      style={{ height: `${barHeight}px` }}
                    />
                  </div>

                  <div className={`text-sm font-bold ${isCheapest ? "text-emerald-700" : ""}`}>
                    {fmtPrice(m.avgPrice)}
                  </div>
                  <div className="text-[9px] text-muted-foreground">avg</div>

                  <div className="text-[10px] text-muted-foreground mt-1">
                    From {fmtPrice(m.cheapestPrice)}
                  </div>
                  <div className="text-[9px] text-muted-foreground">
                    {m.datesWithFlights} dates &middot; {m.datesWithDirect} direct
                  </div>

                  {m.cheapestDate && (
                    <div className="text-[9px] text-primary mt-0.5 font-medium">
                      Best: {new Date(m.cheapestDate + "T00:00:00").toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {savings > 50 && cheapestMonth.cheapestDate && (
            <div className="mt-2 rounded-md bg-emerald-50 border border-emerald-200 px-2.5 py-1.5 text-[10px] text-emerald-800">
              Flying in {cheapestMonth.label} could save {fmtPrice(savings)} per leg.
              Cheapest date: {new Date(cheapestMonth.cheapestDate + "T00:00:00").toLocaleDateString("en-US", {
                weekday: "short",
                month: "short",
                day: "numeric",
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
