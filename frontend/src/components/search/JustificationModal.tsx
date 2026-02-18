import { useState } from "react";
import { Button } from "@/components/ui/button";
import { formatPrice } from "@/lib/currency";
import { formatShortDate as fmtDate } from "@/lib/dates";

interface Alternative {
  type: string;
  label: string;
  airline: string;
  date: string;
  price: number;
  savings: number;
  stops: number;
  duration_minutes: number;
  flight_option_id: string;
  origin_airport?: string;
  destination_airport?: string;
}

interface LegAnalysis {
  leg_id: string;
  sequence: number;
  route: string;
  preferred_date?: string | null;
  justification_required: boolean;
  selected: {
    airline: string;
    date: string;
    price: number;
    stops: number;
    duration_minutes: number;
    flight_option_id: string;
  } | null;
  savings: {
    amount: number;
    percent: number;
  };
  alternatives: Alternative[];
}

interface TripTotals {
  selected: number;
  cheapest: number;
  savings_amount: number;
  savings_percent: number;
}

interface TripWindowFlight {
  airline_name: string;
  airline_code: string;
  price: number;
  stops: number;
}

interface TripWindowProposal {
  outbound_date: string;
  return_date: string;
  trip_duration: number;
  outbound_flight: TripWindowFlight;
  return_flight: TripWindowFlight;
  total_price: number;
  savings: number;
  savings_percent: number;
  same_airline: boolean;
  airline_name: string | null;
}

interface TripWindowAlternatives {
  original_trip_duration: number;
  original_total_price: number;
  proposals: TripWindowProposal[];
}

interface CheaperMonthSuggestion {
  month: string;
  avg_price: number;
  min_price: number;
  current_month_avg: number;
  savings_percent: number;
}

interface AnalysisResult {
  justification_required: boolean;
  // Single-leg fields (backward compat)
  selected?: {
    airline: string;
    date: string;
    price: number;
    stops: number;
    duration_minutes: number;
    flight_option_id: string;
  };
  savings?: {
    amount: number;
    percent: number;
  };
  alternatives?: Alternative[];
  justification_prompt: string | null;
  // Multi-leg fields
  legs?: LegAnalysis[];
  trip_totals?: TripTotals;
  // Trip-window alternatives (shift entire trip)
  trip_window_alternatives?: TripWindowAlternatives | null;
  // Cheaper month suggestions
  cheaper_month_suggestions?: CheaperMonthSuggestion[];
}

interface Props {
  analysis: AnalysisResult;
  onConfirm: (justification: string) => void;
  onSwitch: (flightOptionId: string, legId?: string) => void;
  onSwitchTripWindow?: (proposal: TripWindowProposal) => void;
  onCancel: () => void;
  confirming?: boolean;
  /** "inline" renders as a banner (for $100-500), "modal" renders full overlay (for >$500) */
  mode?: "inline" | "modal";
}

const PRESETS = [
  "Schedule alignment with meetings",
  "Loyalty program / status",
  "Nonstop preference",
  "Red-eye avoidance",
  "Same-day arrival required",
  "Connecting flight risk (tight layover)",
  "Client / customer requirement",
  "Company-negotiated fare",
  "Personal safety / comfort",
];

function fmtPrice(price: number): string {
  return formatPrice(price);
}

function fmtDuration(minutes: number): string {
  if (!minutes) return "—";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h ${m}m`;
}

function savingsColor(amount: number): string {
  if (amount >= 500) return "bg-blue-100 text-blue-800 border-blue-200";
  if (amount >= 200) return "bg-sky-100 text-sky-800 border-sky-200";
  return "bg-slate-100 text-slate-700 border-slate-200";
}

/** Comparison table — Selected vs Cheapest alternative */
function ComparisonTable({
  selected,
  cheapest,
}: {
  selected: NonNullable<AnalysisResult["selected"]>;
  cheapest: Alternative;
}) {
  const rows: { label: string; selected: string; cheapest: string; selectedWins: boolean }[] = [
    {
      label: "Airline",
      selected: selected.airline,
      cheapest: cheapest.airline,
      selectedWins: false,
    },
    {
      label: "Date",
      selected: fmtDate(selected.date),
      cheapest: fmtDate(cheapest.date),
      selectedWins: false,
    },
    {
      label: "Price",
      selected: fmtPrice(selected.price),
      cheapest: fmtPrice(cheapest.price),
      selectedWins: selected.price <= cheapest.price,
    },
    {
      label: "Stops",
      selected: selected.stops === 0 ? "Nonstop" : `${selected.stops} stop${selected.stops > 1 ? "s" : ""}`,
      cheapest: cheapest.stops === 0 ? "Nonstop" : `${cheapest.stops} stop${cheapest.stops > 1 ? "s" : ""}`,
      selectedWins: selected.stops < cheapest.stops,
    },
    {
      label: "Duration",
      selected: fmtDuration(selected.duration_minutes),
      cheapest: fmtDuration(cheapest.duration_minutes),
      selectedWins: selected.duration_minutes > 0 && selected.duration_minutes < cheapest.duration_minutes,
    },
  ];

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-muted/50">
            <th className="text-left px-3 py-1.5 font-medium text-muted-foreground" />
            <th className="text-center px-3 py-1.5 font-semibold">Your Pick</th>
            <th className="text-center px-3 py-1.5 font-semibold text-emerald-700">Lowest Fare</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-t border-border/50">
              <td className="px-3 py-1.5 text-muted-foreground font-medium">{r.label}</td>
              <td className={`px-3 py-1.5 text-center ${r.selectedWins ? "font-semibold text-emerald-700" : ""}`}>
                {r.selected}
                {r.selectedWins && <span className="ml-1 text-[10px]">&#10003;</span>}
              </td>
              <td className={`px-3 py-1.5 text-center ${!r.selectedWins && r.label === "Price" ? "font-semibold text-emerald-700" : ""}`}>
                {r.cheapest}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function JustificationModal({
  analysis,
  onConfirm,
  onSwitch,
  onSwitchTripWindow,
  onCancel,
  confirming = false,
  mode = "modal",
}: Props) {
  const [justification, setJustification] = useState("");
  const [selectedPresets, setSelectedPresets] = useState<Set<string>>(new Set());
  const [showCustom, setShowCustom] = useState(false);

  // Combined justification text
  const presetText = Array.from(selectedPresets).join("; ");
  const fullJustification = [presetText, justification.trim()].filter(Boolean).join(" — ");
  const savingsAmount = analysis.trip_totals?.savings_amount ?? analysis.savings?.amount ?? 0;
  const savingsPercent = analysis.trip_totals?.savings_percent ?? analysis.savings?.percent ?? 0;
  const isHighSavings = savingsAmount >= 500;
  const isMultiLeg = !!(analysis.legs && analysis.legs.length > 0);
  const canConfirm = isHighSavings
    ? fullJustification.length >= 10
    : fullJustification.length > 0;

  function togglePreset(preset: string) {
    setSelectedPresets((prev) => {
      const next = new Set(prev);
      if (next.has(preset)) next.delete(preset);
      else next.add(preset);
      return next;
    });
  }

  // For single-leg mode
  const cheapestAlt = analysis.alternatives?.[0];
  // For multi-leg mode: find leg with biggest savings
  const biggestSavingsLeg = isMultiLeg
    ? analysis.legs!.reduce((best, leg) =>
        leg.savings.amount > (best?.savings.amount ?? 0) ? leg : best,
      analysis.legs![0])
    : null;

  // ---- Inline banner mode (for $100-$500) ----
  if (mode === "inline") {
    // For multi-leg inline: show trip savings + biggest savings leg
    const inlineSavings = savingsAmount;
    const inlineAlt = isMultiLeg
      ? biggestSavingsLeg?.alternatives[0]
      : cheapestAlt;
    const inlineLegId = isMultiLeg ? biggestSavingsLeg?.leg_id : undefined;

    return (
      <div className="rounded-lg border border-blue-200 bg-blue-50/40 p-3 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold ${savingsColor(inlineSavings)}`}>
              {fmtPrice(inlineSavings)} {isMultiLeg ? "lower-fare combination" : "lower fare"} available
            </span>
            {inlineAlt && (
              <span className="text-xs text-muted-foreground">
                {isMultiLeg && biggestSavingsLeg ? `${biggestSavingsLeg.route}: ` : ""}
                {inlineAlt.airline} at {fmtPrice(inlineAlt.price)}
              </span>
            )}
          </div>
          {inlineAlt && (
            <Button
              size="sm"
              variant="outline"
              className="text-xs h-7"
              onClick={() => onSwitch(inlineAlt.flight_option_id, inlineLegId)}
            >
              Switch
            </Button>
          )}
        </div>

        {/* Preset chips */}
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => togglePreset(p)}
              className={`text-[11px] px-2.5 py-1 rounded-full transition-all ${
                selectedPresets.has(p)
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-white border border-border text-foreground hover:bg-muted/50"
              }`}
            >
              {p}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setShowCustom(!showCustom)}
            className="text-[11px] px-2.5 py-1 rounded-full bg-white border border-dashed border-border text-muted-foreground hover:text-foreground"
          >
            Other...
          </button>
        </div>

        {selectedPresets.size > 0 && (
          <div className="rounded-md bg-primary/5 border border-primary/20 px-2.5 py-1.5 text-[11px] text-foreground">
            <span className="font-medium text-primary">Selected:</span>{" "}
            {Array.from(selectedPresets).join("; ")}
          </div>
        )}

        {showCustom && (
          <input
            type="text"
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
            placeholder="Custom reason..."
            className="w-full rounded-md border border-border bg-white px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        )}

        <div className="flex items-center justify-between">
          <p className="text-[10px] text-muted-foreground">
            {canConfirm ? "Your note will be included with your travel request" : "Tap a reason or add your own"}
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={onCancel}>
              Cancel
            </Button>
            <Button
              size="sm"
              className="h-7 text-xs"
              disabled={!canConfirm || confirming}
              onClick={() => onConfirm(fullJustification)}
            >
              {confirming ? "Saving..." : "Confirm"}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // ---- Full modal mode (for >$500) ----
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onCancel}
      />

      <div className="relative bg-card rounded-xl shadow-2xl border border-border max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="px-5 pt-5 pb-3">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="text-base font-semibold">We found some alternatives</h3>
              {isMultiLeg && analysis.trip_totals ? (
                <p className="text-xs text-muted-foreground mt-0.5">
                  Trip total: {fmtPrice(analysis.trip_totals.selected)} (lowest available: {fmtPrice(analysis.trip_totals.cheapest)})
                </p>
              ) : analysis.selected ? (
                <p className="text-xs text-muted-foreground mt-0.5">
                  {analysis.selected.airline} on {fmtDate(analysis.selected.date)}{" "}
                  at {fmtPrice(analysis.selected.price)}
                </p>
              ) : null}
            </div>
            <span className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold ${savingsColor(savingsAmount)}`}>
              {fmtPrice(savingsAmount)} difference ({savingsPercent}%)
            </span>
          </div>
        </div>

        {/* LLM prompt */}
        {analysis.justification_prompt && (
          <div className="mx-5 rounded-lg border border-blue-200 bg-blue-50/80 p-3 text-sm text-blue-800 leading-relaxed">
            {analysis.justification_prompt}
          </div>
        )}

        {/* Trip-window alternatives — shift entire trip, preserve duration */}
        {isMultiLeg && analysis.trip_window_alternatives && analysis.trip_window_alternatives.proposals.length > 0 && (
          <div className="mx-5 mt-4 rounded-lg border border-blue-200 bg-blue-50/30">
            <div className="px-3 py-2 border-b border-blue-100">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-blue-700">
                Shift Your Entire Trip
              </h4>
              <p className="text-[10px] text-blue-600 mt-0.5">
                Same {analysis.trip_window_alternatives.original_trip_duration}-day trip, different dates
              </p>
            </div>
            {analysis.trip_window_alternatives.proposals.slice(0, 3).map((proposal) => (
              <div
                key={`${proposal.outbound_date}-${proposal.return_date}`}
                className="flex items-center justify-between px-3 py-2.5 border-b border-blue-100/50 last:border-b-0"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 text-xs">
                    <span className="font-medium">{fmtDate(proposal.outbound_date)}</span>
                    <span className="text-muted-foreground">&rarr;</span>
                    <span className="font-medium">{fmtDate(proposal.return_date)}</span>
                    <span className="text-[10px] text-muted-foreground ml-1">
                      ({proposal.trip_duration}d)
                    </span>
                    {proposal.same_airline && proposal.airline_name && (
                      <span className={`text-[9px] rounded-full px-1.5 py-0.5 ${
                        proposal.user_airline
                          ? "bg-primary/10 text-primary font-medium"
                          : "bg-blue-100 text-blue-700"
                      }`}>
                        {proposal.user_airline ? `✓ ${proposal.airline_name}` : proposal.airline_name}
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] text-muted-foreground flex gap-2 mt-0.5">
                    <span>
                      Out: {proposal.outbound_flight.airline_name} {fmtPrice(proposal.outbound_flight.price)}
                      {proposal.outbound_flight.stops === 0 ? " (nonstop)" : ` (${proposal.outbound_flight.stops} stop)`}
                    </span>
                    <span>
                      Ret: {proposal.return_flight.airline_name} {fmtPrice(proposal.return_flight.price)}
                      {proposal.return_flight.stops === 0 ? " (nonstop)" : ` (${proposal.return_flight.stops} stop)`}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <div className="text-right">
                    <div className="text-sm font-bold">{fmtPrice(proposal.total_price)}</div>
                    <div className={`text-[10px] font-semibold ${
                      proposal.savings >= 0 ? "text-blue-700" : "text-amber-600"
                    }`}>
                      {proposal.savings >= 0
                        ? `Save ${fmtPrice(proposal.savings)} (${proposal.savings_percent}%)`
                        : `${fmtPrice(Math.abs(proposal.savings))} more (${Math.abs(proposal.savings_percent)}%)`
                      }
                    </div>
                  </div>
                  {onSwitchTripWindow && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onSwitchTripWindow(proposal)}
                      className="text-xs"
                    >
                      Switch
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Cheaper month suggestions */}
        {analysis.cheaper_month_suggestions && analysis.cheaper_month_suggestions.length > 0 && (
          <div className="mx-5 mt-3 rounded-lg border border-amber-200 bg-amber-50/30 px-3 py-2.5">
            <h4 className="text-[10px] font-semibold uppercase tracking-wide text-amber-700 mb-1.5">
              Flexible dates? Same airline, cheaper months
            </h4>
            {analysis.cheaper_month_suggestions.map((s) => (
              <div key={s.month} className="flex items-center justify-between text-xs py-1">
                <span className="font-medium">{s.month}</span>
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">
                    avg {fmtPrice(s.avg_price)} (from {fmtPrice(s.min_price)})
                  </span>
                  <span className="text-[10px] font-semibold text-amber-700">
                    {s.savings_percent}% cheaper
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Multi-leg per-leg sections */}
        {isMultiLeg ? (
          <div className="px-5 pt-4 space-y-5">
            {analysis.legs!.map((leg) => {
              if (!leg.selected) return null;
              const legCheapest = leg.alternatives[0];
              return (
                <div key={leg.leg_id} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold uppercase tracking-wide">
                      Leg {leg.sequence}: {leg.route}
                    </h4>
                    {leg.savings.amount > 0 && (
                      <span className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${savingsColor(leg.savings.amount)}`}>
                        {fmtPrice(leg.savings.amount)} diff
                      </span>
                    )}
                  </div>

                  {/* Comparison table for this leg */}
                  {legCheapest && (
                    <ComparisonTable selected={leg.selected} cheapest={legCheapest} />
                  )}

                  {/* Alternative cards for this leg */}
                  {leg.alternatives.length > 0 && (
                    <div className="space-y-1.5">
                      {leg.alternatives.map((alt) => (
                        <div
                          key={alt.flight_option_id}
                          className="flex items-center justify-between rounded-lg border border-border bg-muted/20 px-3 py-2 hover:bg-muted/40 transition-colors"
                        >
                          <div>
                            <div className="text-sm font-medium">{alt.airline}</div>
                            <div className="text-xs text-muted-foreground">
                              {alt.label} &middot; {fmtDate(alt.date)} &middot;{" "}
                              {alt.stops === 0
                                ? "Nonstop"
                                : `${alt.stops} stop${alt.stops > 1 ? "s" : ""}`}
                              {alt.duration_minutes > 0 &&
                                ` · ${fmtDuration(alt.duration_minutes)}`}
                            </div>
                          </div>
                          <div className="flex items-center gap-3">
                            <div className="text-right">
                              <div className="text-sm font-bold text-emerald-700">
                                {fmtPrice(alt.price)}
                              </div>
                              <div className="text-[10px] text-emerald-600">
                                {fmtPrice(alt.savings)} less
                              </div>
                            </div>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => onSwitch(alt.flight_option_id, leg.leg_id)}
                              className="text-xs"
                            >
                              Switch
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <>
            {/* Single-leg: side-by-side comparison */}
            {cheapestAlt && analysis.selected && (
              <div className="px-5 pt-4">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  Comparison
                </h4>
                <ComparisonTable selected={analysis.selected} cheapest={cheapestAlt} />
              </div>
            )}

            {/* Single-leg: alternative cards */}
            {analysis.alternatives && analysis.alternatives.length > 0 && (
              <div className="px-5 pt-4 space-y-2">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  Other options on this route
                </h4>
                {analysis.alternatives.map((alt) => (
                  <div
                    key={alt.flight_option_id}
                    className="flex items-center justify-between rounded-lg border border-border bg-muted/20 px-3 py-2.5 hover:bg-muted/40 transition-colors"
                  >
                    <div>
                      <div className="text-sm font-medium">{alt.airline}</div>
                      <div className="text-xs text-muted-foreground">
                        {alt.label} &middot; {fmtDate(alt.date)} &middot;{" "}
                        {alt.stops === 0
                          ? "Nonstop"
                          : `${alt.stops} stop${alt.stops > 1 ? "s" : ""}`}
                        {alt.duration_minutes > 0 &&
                          ` · ${fmtDuration(alt.duration_minutes)}`}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <div className="text-sm font-bold text-emerald-700">
                          {fmtPrice(alt.price)}
                        </div>
                        <div className="text-[10px] text-emerald-600">
                          save {fmtPrice(alt.savings)}
                        </div>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onSwitch(alt.flight_option_id)}
                        className="text-xs"
                      >
                        Switch
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* Quick-justify presets */}
        <div className="px-5 pt-4 space-y-2">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Add a note for your approver
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {PRESETS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => togglePreset(p)}
                className={`text-[11px] px-2.5 py-1 rounded-full transition-all ${
                  selectedPresets.has(p)
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Selected reasons summary + free-text */}
        <div className="px-5 pt-3 space-y-1.5">
          {selectedPresets.size > 0 && (
            <div className="rounded-md bg-primary/5 border border-primary/20 px-3 py-2 text-xs text-foreground">
              <span className="font-medium text-primary">Selected:</span>{" "}
              {Array.from(selectedPresets).join("; ")}
            </div>
          )}
          <textarea
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
            placeholder={selectedPresets.size > 0 ? "Add any additional context (optional)..." : "Add a note about your preference..."}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm min-h-[60px] resize-y focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          <p className="text-[10px] text-muted-foreground">
            {isHighSavings && fullJustification.length < 10
              ? `A note is needed for differences over $500 (${fullJustification.length}/10 chars)`
              : canConfirm
              ? "This note will be included with your travel request"
              : "Tap a reason above or add your own note"}
          </p>
        </div>

        {/* Actions */}
        <div className="px-5 pt-4 pb-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!canConfirm || confirming}
            onClick={() => onConfirm(fullJustification)}
          >
            {confirming ? "Saving..." : "Confirm Selection"}
          </Button>
        </div>
      </div>
    </div>
  );
}
