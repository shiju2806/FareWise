import { useEffect, useMemo, useState } from "react";
import type { TripLeg } from "@/types/trip";
import type { FlightOption } from "@/types/flight";
import type { SearchResult } from "@/types/search";
import apiClient from "@/api/client";
import { formatPrice } from "@/lib/currency";

interface Props {
  tripId: string;
  legs: TripLeg[];
  selectedFlights: Record<string, FlightOption>;
  results: Record<string, SearchResult>;
  activeLegIndex: number;
  onLegClick: (index: number) => void;
}

/** Per-cabin-class daily policy budgets (one-way, USD) — mirrors backend */
const POLICY_BUDGET: Record<string, number> = {
  economy: 600,
  premium_economy: 1100,
  business: 2000,
  first: 4500,
};

const fmtPrice = (n: number, currency?: string) => formatPrice(n, currency || "USD");

interface LegComparison {
  legId: string;
  selected: FlightOption | null;
  cheapestDirect: FlightOption | null;
  cheapestWithStops: FlightOption | null;
  cheapestOverall: FlightOption | null;
  policyBudget: number;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
interface TripAnalysis {
  summary: string;
  recommendation: "approve" | "review" | "optimize";
  key_insight: string;
  total_assessment: string;
  justification_prompt: string | null;
}

export function TripCostBar({ tripId, legs, selectedFlights, results, activeLegIndex, onLegClick }: Props) {
  const [analysis, setAnalysis] = useState<TripAnalysis | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);

  const comparisons = useMemo<LegComparison[]>(() => {
    return legs.map((leg) => {
      const sel = selectedFlights[leg.id] || null;
      const opts = results[leg.id]?.all_options || [];
      const budget = POLICY_BUDGET[leg.cabin_class] || POLICY_BUDGET.economy;

      let cheapestDirect: FlightOption | null = null;
      let cheapestWithStops: FlightOption | null = null;
      let cheapestOverall: FlightOption | null = null;

      for (const f of opts) {
        if (!cheapestOverall || f.price < cheapestOverall.price) cheapestOverall = f;
        if (f.stops === 0 && (!cheapestDirect || f.price < cheapestDirect.price)) cheapestDirect = f;
        if (f.stops > 0 && (!cheapestWithStops || f.price < cheapestWithStops.price)) cheapestWithStops = f;
      }

      return { legId: leg.id, selected: sel, cheapestDirect, cheapestWithStops, cheapestOverall, policyBudget: budget };
    });
  }, [legs, selectedFlights, results]);

  const totalSelected = comparisons.reduce((s, c) => s + (c.selected?.price || 0), 0);
  const totalCheapest = comparisons.reduce((s, c) => s + (c.cheapestOverall?.price || 0), 0);
  const totalCheapestStops = comparisons.reduce((s, c) => {
    const p = c.cheapestWithStops?.price || c.cheapestOverall?.price || 0;
    return s + p;
  }, 0);
  const totalPolicy = comparisons.reduce((s, c) => s + c.policyBudget, 0);

  const allSelected = comparisons.every((c) => c.selected !== null);
  const anySelected = comparisons.some((c) => c.selected !== null);

  // Fetch LLM trip analysis when all legs are selected
  useEffect(() => {
    if (!allSelected || !tripId) {
      setAnalysis(null);
      return;
    }

    let cancelled = false;
    setLoadingAnalysis(true);

    const selectedMap: Record<string, string> = {};
    for (const leg of legs) {
      const flight = selectedFlights[leg.id];
      if (flight) selectedMap[leg.id] = flight.id;
    }

    apiClient
      .post(`/trips/${tripId}/analyze-trip`, { selected_flights: selectedMap })
      .then((res) => {
        if (!cancelled) {
          setAnalysis(res.data?.analysis || null);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoadingAnalysis(false);
      });

    return () => { cancelled = true; };
  }, [allSelected, tripId, legs, selectedFlights]);

  if (!anySelected && legs.length <= 1) return null;

  const savingsVsCheapest = totalSelected - totalCheapest;
  const policyDiff = totalSelected - totalPolicy;

  const recommendationColor = analysis?.recommendation === "approve"
    ? "text-emerald-700 bg-emerald-50"
    : analysis?.recommendation === "optimize"
    ? "text-red-700 bg-red-50"
    : "text-amber-700 bg-amber-50";

  return (
    <div className="rounded-lg border border-border bg-card shadow-sm overflow-hidden">
      {/* Per-leg breakdown */}
      <div className="flex divide-x divide-border">
        {comparisons.map((c, i) => {
          const leg = legs[i];
          const isActive = i === activeLegIndex;
          return (
            <button
              key={c.legId}
              type="button"
              onClick={() => onLegClick(i)}
              className={`flex-1 px-3 py-2.5 text-left transition-colors hover:bg-muted/40 ${
                isActive ? "bg-primary/5 border-b-2 border-primary" : ""
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wide">
                  Leg {i + 1}: {leg.origin_airport} &rarr; {leg.destination_airport}
                </span>
                {c.selected && (
                  <span className="text-[9px] text-emerald-600 font-medium">Selected</span>
                )}
              </div>

              {c.selected ? (
                <div className="mt-1">
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-bold">{fmtPrice(c.selected.price, c.selected.currency)}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {c.selected.airline_name} &middot; {c.selected.stops === 0 ? "Nonstop" : `${c.selected.stops} stop`}
                    </span>
                  </div>
                  {c.cheapestOverall && c.selected.price > c.cheapestOverall.price + 10 && (
                    <div className="text-[10px] text-amber-600 mt-0.5">
                      Cheapest: {fmtPrice(c.cheapestOverall.price, c.cheapestOverall.currency)} ({c.cheapestOverall.airline_name})
                    </div>
                  )}
                </div>
              ) : (
                <div className="mt-1 text-xs text-muted-foreground">
                  {results[c.legId] ? (
                    <span>
                      From {fmtPrice(c.cheapestOverall?.price || 0, c.cheapestOverall?.currency)} &middot; Select a flight
                    </span>
                  ) : (
                    <span>Search pending</span>
                  )}
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Trip total summary */}
      {anySelected && (
        <div className="border-t border-border bg-muted/20 px-3 py-2 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-4">
            <div>
              <span className="text-[10px] text-muted-foreground font-medium uppercase">Trip Total</span>
              <span className="ml-2 text-base font-bold">
                {allSelected ? fmtPrice(totalSelected) : `~${fmtPrice(totalSelected)}+`}
              </span>
              {!allSelected && (
                <span className="text-[10px] text-muted-foreground ml-1">
                  ({comparisons.filter((c) => c.selected).length}/{legs.length} legs)
                </span>
              )}
            </div>

            {/* Comparison badges */}
            {allSelected && totalCheapest > 0 && savingsVsCheapest > 10 && (
              <span className={`inline-flex items-center text-[10px] font-medium px-2 py-0.5 rounded-md ${
                savingsVsCheapest >= 500 ? "bg-red-100 text-red-700" :
                savingsVsCheapest >= 200 ? "bg-amber-100 text-amber-700" :
                "bg-muted text-muted-foreground"
              }`}>
                {fmtPrice(savingsVsCheapest)} vs cheapest combo
              </span>
            )}

            {allSelected && totalCheapestStops > 0 && totalCheapestStops < totalSelected - 10 && (
              <span className="inline-flex items-center text-[10px] font-medium px-2 py-0.5 rounded-md bg-blue-50 text-blue-700">
                {fmtPrice(totalSelected - totalCheapestStops)} saveable with stops
              </span>
            )}

            {allSelected && (
              <span className={`inline-flex items-center text-[10px] font-medium px-2 py-0.5 rounded-md ${
                policyDiff > 0 ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-700"
              }`}>
                {policyDiff > 0
                  ? `${fmtPrice(policyDiff)} over policy`
                  : `${fmtPrice(Math.abs(policyDiff))} under policy`
                }
              </span>
            )}

            {/* LLM recommendation badge */}
            {analysis && (
              <span className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-md ${recommendationColor}`}>
                {analysis.recommendation === "approve" ? "Approved" :
                 analysis.recommendation === "optimize" ? "Optimize" : "Review"}
              </span>
            )}
          </div>

          {allSelected && (
            <div className="text-[10px] text-muted-foreground">
              Policy: {fmtPrice(totalPolicy)} &middot; Cheapest: {fmtPrice(totalCheapest)}
            </div>
          )}
        </div>
      )}

      {/* LLM insight banner */}
      {analysis && analysis.key_insight && (
        <div className={`border-t px-3 py-2 text-[11px] ${
          analysis.recommendation === "approve"
            ? "border-emerald-200 bg-emerald-50/50 text-emerald-800"
            : analysis.recommendation === "optimize"
            ? "border-red-200 bg-red-50/50 text-red-800"
            : "border-amber-200 bg-amber-50/50 text-amber-800"
        }`}>
          {analysis.key_insight}
        </div>
      )}

      {loadingAnalysis && (
        <div className="border-t border-border px-3 py-1.5 flex items-center gap-2">
          <div className="h-3 w-3 animate-spin rounded-full border border-primary border-t-transparent" />
          <span className="text-[10px] text-muted-foreground">Analyzing trip cost...</span>
        </div>
      )}
    </div>
  );
}
