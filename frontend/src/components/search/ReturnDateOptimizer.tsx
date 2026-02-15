import { useEffect, useMemo, useState } from "react";
import type { FlightOption } from "@/types/flight";
import type { SearchResult } from "@/types/search";
import apiClient from "@/api/client";

interface Props {
  tripId: string;
  outboundResult: SearchResult;
  returnResult: SearchResult;
  onSelectCombo: (outboundFlight: FlightOption, returnFlight: FlightOption) => void;
}

interface DateCombo {
  outDate: string;
  retDate: string;
  outFlight: FlightOption;
  retFlight: FlightOption;
  totalPrice: number;
  outStops: number;
  retStops: number;
}

interface LLMInsight {
  date_insight: string;
  flexibility_advice: string;
  best_combo: {
    outbound_date: string;
    return_date: string;
    total_price: number;
    savings_vs_preferred: number;
    reason: string;
  } | null;
}

function fmtPrice(n: number): string {
  return `$${Math.round(n).toLocaleString()}`;
}

function fmtShortDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", weekday: "short" });
}

export function ReturnDateOptimizer({ tripId, outboundResult, returnResult, onSelectCombo }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [llmInsight, setLlmInsight] = useState<LLMInsight | null>(null);
  const [loadingInsight, setLoadingInsight] = useState(false);

  // Compute combos from frontend data (fast, immediate)
  const combos = useMemo<DateCombo[]>(() => {
    const outByDate = new Map<string, FlightOption>();
    for (const f of outboundResult.all_options) {
      const d = f.departure_time.slice(0, 10);
      if (!outByDate.has(d) || f.price < outByDate.get(d)!.price) {
        outByDate.set(d, f);
      }
    }

    const retByDate = new Map<string, FlightOption>();
    for (const f of returnResult.all_options) {
      const d = f.departure_time.slice(0, 10);
      if (!retByDate.has(d) || f.price < retByDate.get(d)!.price) {
        retByDate.set(d, f);
      }
    }

    const results: DateCombo[] = [];
    for (const [outDate, outFlight] of outByDate) {
      for (const [retDate, retFlight] of retByDate) {
        if (retDate <= outDate) continue;
        results.push({
          outDate,
          retDate,
          outFlight,
          retFlight,
          totalPrice: outFlight.price + retFlight.price,
          outStops: outFlight.stops,
          retStops: retFlight.stops,
        });
      }
    }

    results.sort((a, b) => a.totalPrice - b.totalPrice);
    return results.slice(0, 10);
  }, [outboundResult.all_options, returnResult.all_options]);

  // Fetch LLM date optimization insights
  useEffect(() => {
    if (!tripId || combos.length < 2) return;
    let cancelled = false;
    setLoadingInsight(true);

    apiClient
      .post(`/trips/${tripId}/optimize-dates`, {})
      .then((res) => {
        if (!cancelled) {
          setLlmInsight(res.data || null);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoadingInsight(false);
      });

    return () => { cancelled = true; };
  }, [tripId, combos.length]);

  if (combos.length < 2) return null;

  const cheapest = combos[0];
  const displayCombos = expanded ? combos : combos.slice(0, 5);

  return (
    <div className="rounded-lg border border-border bg-card shadow-sm">
      <div className="px-3 py-2 border-b border-border flex items-center justify-between">
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Round-Trip Date Optimizer
          </h4>
          <p className="text-[10px] text-muted-foreground mt-0.5">
            Best outbound + return date combinations by total price
          </p>
        </div>
        <span className="text-xs font-bold text-emerald-700">
          Best: {fmtPrice(cheapest.totalPrice)}
        </span>
      </div>

      {/* LLM insight banner */}
      {llmInsight && llmInsight.date_insight && (
        <div className="px-3 py-2 border-b border-blue-100 bg-blue-50/50 text-[11px] text-blue-800">
          {llmInsight.date_insight}
          {llmInsight.flexibility_advice && (
            <span className="ml-1 font-medium">{llmInsight.flexibility_advice}</span>
          )}
        </div>
      )}

      {loadingInsight && (
        <div className="px-3 py-1.5 border-b border-border flex items-center gap-2">
          <div className="h-3 w-3 animate-spin rounded-full border border-primary border-t-transparent" />
          <span className="text-[10px] text-muted-foreground">AI analyzing date patterns...</span>
        </div>
      )}

      <div className="divide-y divide-border/50">
        {displayCombos.map((combo, i) => {
          const savingsVsBest = combo.totalPrice - cheapest.totalPrice;
          const isBest = i === 0;
          return (
            <div
              key={`${combo.outDate}-${combo.retDate}`}
              className={`flex items-center justify-between px-3 py-2 hover:bg-muted/30 transition-colors ${
                isBest ? "bg-emerald-50/50" : ""
              }`}
            >
              <div className="flex items-center gap-4 min-w-0">
                <span className="text-[10px] text-muted-foreground w-4 shrink-0">
                  {i + 1}.
                </span>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 text-xs">
                    <span className="font-medium">{fmtShortDate(combo.outDate)}</span>
                    <span className="text-muted-foreground">&rarr;</span>
                    <span className="font-medium">{fmtShortDate(combo.retDate)}</span>
                    <span className="text-[10px] text-muted-foreground ml-1">
                      ({Math.round((new Date(combo.retDate).getTime() - new Date(combo.outDate).getTime()) / 86400000)}d)
                    </span>
                  </div>
                  <div className="text-[10px] text-muted-foreground flex gap-2 mt-0.5">
                    <span>
                      Out: {combo.outFlight.airline_name}
                      {combo.outStops > 0 ? ` (${combo.outStops} stop)` : " (nonstop)"}
                    </span>
                    <span>
                      Ret: {combo.retFlight.airline_name}
                      {combo.retStops > 0 ? ` (${combo.retStops} stop)` : " (nonstop)"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3 shrink-0">
                <div className="text-right">
                  <div className={`text-sm font-bold ${isBest ? "text-emerald-700" : ""}`}>
                    {fmtPrice(combo.totalPrice)}
                  </div>
                  {savingsVsBest > 0 && (
                    <div className="text-[10px] text-muted-foreground">
                      +{fmtPrice(savingsVsBest)}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => onSelectCombo(combo.outFlight, combo.retFlight)}
                  className="text-[10px] text-primary hover:underline font-medium shrink-0"
                >
                  Select
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {combos.length > 5 && (
        <div className="border-t border-border px-3 py-1.5">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-[10px] text-primary hover:underline w-full text-center"
          >
            {expanded ? "Show fewer" : `Show ${combos.length - 5} more combos`}
          </button>
        </div>
      )}
    </div>
  );
}
