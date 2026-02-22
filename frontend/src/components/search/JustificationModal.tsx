import { useState } from "react";
import { Button } from "@/components/ui/button";
import { formatPrice } from "@/lib/currency";
import { formatShortDate as fmtDate } from "@/lib/dates";
import type { TripWindowProposal, TripWindowAlternatives } from "@/types/search";
import type { FlightOption } from "@/types/flight";
import type { TripLeg } from "@/types/trip";

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
  departure_time?: string;
  /** LLM-curated explanation for why this alternative is suggested */
  reason?: string;
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
  // Trip-window alternatives (shift entire trip + different month)
  trip_window_alternatives?: TripWindowAlternatives | null;
  // Cabin downgrade suggestion
  cabin_downgrade_suggestion?: {
    current_cabin: string;
    suggested_cabin: string;
    current_total: number;
    suggested_total: number;
    savings_amount: number;
    savings_percent: number;
  } | null;
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
  /** True after user clicked Switch — shows simplified confirm view */
  hasSwitched?: boolean;
  /** Updated trip total after switch */
  currentTotal?: number;
  /** Current selected flights per leg (for post-switch detail view) */
  switchedFlights?: Record<string, FlightOption>;
  /** Trip legs (for route labels in post-switch view) */
  legs?: TripLeg[];
  /** Callback when user wants to switch cabin class */
  onCabinDowngrade?: (suggestedCabin: string) => void;
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

function fmtDuration(minutes: number): string {
  if (!minutes) return "—";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h ${m}m`;
}

function cabinLabel(cabin: string): string {
  const labels: Record<string, string> = {
    economy: "Economy",
    premium_economy: "Premium Economy",
    business: "Business",
    first: "First",
  };
  return labels[cabin] || cabin;
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
      selected: formatPrice(selected.price),
      cheapest: formatPrice(cheapest.price),
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

/** Preset chips + textarea for justification notes */
function JustificationSection({
  selectedPresets,
  togglePreset,
  justification,
  setJustification,
  isHighSavings,
  canConfirm,
  fullJustification,
}: {
  selectedPresets: Set<string>;
  togglePreset: (p: string) => void;
  justification: string;
  setJustification: (v: string) => void;
  isHighSavings: boolean;
  canConfirm: boolean;
  fullJustification: string;
}) {
  return (
    <div className="space-y-2">
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
  hasSwitched = false,
  currentTotal,
  switchedFlights,
  legs,
  onCabinDowngrade,
}: Props) {
  const [justification, setJustification] = useState("");
  const [selectedPresets, setSelectedPresets] = useState<Set<string>>(new Set());
  const [showCustom, setShowCustom] = useState(false);
  const [expandedProposals, setExpandedProposals] = useState(false);
  const [expandedSameDay, setExpandedSameDay] = useState(false);
  const [expandedDiffMonth, setExpandedDiffMonth] = useState(false);

  /** Format "2026-03-21T08:30:00" → "8:30a" */
  function fmtTime(iso?: string): string {
    if (!iso || iso.length < 16) return "";
    const h = parseInt(iso.substring(11, 13), 10);
    const m = iso.substring(14, 16);
    const ampm = h >= 12 ? "p" : "a";
    const h12 = h % 12 || 12;
    return `${h12}:${m}${ampm}`;
  }

  /** Format duration in minutes → "7h 15m" */
  function fmtDur(mins?: number): string {
    if (!mins || mins <= 0) return "";
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
  }

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

  // Check if there are any alternatives to show in the right column
  const hasTripWindow = isMultiLeg && analysis.trip_window_alternatives && analysis.trip_window_alternatives.proposals.length > 0;
  const hasDifferentMonth = isMultiLeg
    && analysis.trip_window_alternatives?.different_month
    && analysis.trip_window_alternatives.different_month.length > 0;
  const hasLegAlternatives = isMultiLeg
    ? analysis.legs!.some((leg) => leg.alternatives.length > 0)
    : (analysis.alternatives && analysis.alternatives.length > 0);
  const hasCabinDowngrade = !!analysis.cabin_downgrade_suggestion;
  const hasAlternatives = hasTripWindow || hasDifferentMonth || hasLegAlternatives || hasCabinDowngrade;

  // ---- Inline banner mode (for $100-$500) ----
  if (mode === "inline") {
    const inlineSavings = savingsAmount;
    const inlineAlt = isMultiLeg
      ? biggestSavingsLeg?.alternatives[0]
      : cheapestAlt;
    const inlineLegId = isMultiLeg ? biggestSavingsLeg?.leg_id : undefined;

    return (
      <div className="rounded-lg border border-blue-200 bg-blue-50/40 p-3 space-y-3">
        {hasSwitched ? (
          /* Post-switch inline: confirm with flight details */
          <>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800">
                  &#10003; Selection updated
                </span>
                {currentTotal != null && (
                  <span className="text-sm font-bold">New total: {formatPrice(currentTotal)}</span>
                )}
              </div>
              {switchedFlights && legs && legs.map((leg) => {
                const flight = switchedFlights[leg.id];
                if (!flight) return null;
                return (
                  <div key={leg.id} className="flex items-center justify-between text-xs bg-emerald-50/50 rounded-md px-2.5 py-1.5 border border-emerald-100">
                    <div>
                      <span className="font-medium">{leg.origin_airport}&rarr;{leg.destination_airport}</span>
                      <span className="text-muted-foreground ml-1.5">{flight.airline_name} &middot; {fmtDate(flight.departure_time)}</span>
                    </div>
                    <span className="font-semibold">{formatPrice(flight.price)}</span>
                  </div>
                );
              })}
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
            </div>

            {selectedPresets.size > 0 && (
              <div className="rounded-md bg-primary/5 border border-primary/20 px-2.5 py-1.5 text-[11px] text-foreground">
                <span className="font-medium text-primary">Selected:</span>{" "}
                {Array.from(selectedPresets).join("; ")}
              </div>
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
                  {confirming ? "Saving..." : "Confirm & Review"}
                </Button>
              </div>
            </div>
          </>
        ) : (
          /* Normal inline mode */
          <>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold ${savingsColor(inlineSavings)}`}>
                  {formatPrice(inlineSavings)} {isMultiLeg ? "lower-fare combination" : "lower fare"} available
                </span>
                {inlineAlt && (
                  <span className="text-xs text-muted-foreground">
                    {isMultiLeg && biggestSavingsLeg ? `${biggestSavingsLeg.route}: ` : ""}
                    {inlineAlt.airline} at {formatPrice(inlineAlt.price)}
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
          </>
        )}
      </div>
    );
  }

  // ---- Full modal mode (for >$500) — 2-column layout ----
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onCancel}
      />

      <div className="relative bg-card rounded-xl shadow-2xl border border-border max-w-5xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header — full width */}
        <div className="px-5 pt-5 pb-3">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="text-base font-semibold">
                {hasSwitched ? "Selection Updated" : "Selection Summary"}
              </h3>
              {hasSwitched && currentTotal != null ? (
                <p className="text-xs text-muted-foreground mt-0.5">
                  New trip total: {formatPrice(currentTotal)}
                </p>
              ) : isMultiLeg && analysis.trip_totals ? (
                <p className="text-xs text-muted-foreground mt-0.5">
                  Trip total: {formatPrice(analysis.trip_totals.selected)} (lowest available: {formatPrice(analysis.trip_totals.cheapest)})
                </p>
              ) : analysis.selected ? (
                <p className="text-xs text-muted-foreground mt-0.5">
                  {analysis.selected.airline} on {fmtDate(analysis.selected.date)}{" "}
                  at {formatPrice(analysis.selected.price)}
                </p>
              ) : null}
            </div>
            {hasSwitched ? (
              <span className="inline-flex items-center rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-800">
                &#10003; Updated
              </span>
            ) : (
              <span className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold ${savingsColor(savingsAmount)}`}>
                {formatPrice(savingsAmount)} difference ({savingsPercent}%)
              </span>
            )}
          </div>
        </div>

        {/* Post-switch: confirm view with flight details */}
        {hasSwitched ? (
          <div className="px-5 pb-5 space-y-4">
            {/* Per-leg flight details */}
            {switchedFlights && legs && legs.length > 0 ? (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  New Selection
                </h4>
                {legs.map((leg) => {
                  const flight = switchedFlights[leg.id];
                  if (!flight) return null;
                  return (
                    <div
                      key={leg.id}
                      className="rounded-lg border border-emerald-200 bg-emerald-50/30 p-3"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-xs text-muted-foreground font-medium">
                            Leg {leg.sequence}: {leg.origin_airport} &rarr; {leg.destination_airport}
                          </div>
                          <div className="text-sm font-semibold mt-0.5">
                            {flight.airline_name}
                            <span className="text-muted-foreground font-normal ml-1.5 text-xs">
                              {flight.flight_numbers}
                            </span>
                          </div>
                          <div className="text-xs text-muted-foreground mt-0.5">
                            {fmtDate(flight.departure_time)}
                            {" \u00b7 "}
                            {flight.stops === 0
                              ? "Nonstop"
                              : `${flight.stops} stop${flight.stops > 1 ? "s" : ""}`}
                            {flight.duration_minutes > 0 &&
                              ` \u00b7 ${fmtDuration(flight.duration_minutes)}`}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-base font-bold">{formatPrice(flight.price)}</div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-3 text-sm text-emerald-800">
                Your flight selection has been updated.
              </div>
            )}

            <p className="text-xs text-muted-foreground">
              Add a note for your approver and confirm to proceed to review.
            </p>

            <JustificationSection
              selectedPresets={selectedPresets}
              togglePreset={togglePreset}
              justification={justification}
              setJustification={setJustification}
              isHighSavings={isHighSavings}
              canConfirm={canConfirm}
              fullJustification={fullJustification}
            />

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" size="sm" onClick={onCancel}>
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={!canConfirm || confirming}
                onClick={() => onConfirm(fullJustification)}
              >
                {confirming ? "Saving..." : "Confirm & Review"}
              </Button>
            </div>
          </div>
        ) : (
          /* Normal view: 2-column layout */
          <>
            {/* LLM prompt — full width above the grid */}
            {analysis.justification_prompt && (
              <div className="mx-5 mb-4 rounded-lg border border-blue-200 bg-blue-50/80 p-3 text-sm text-blue-800 leading-relaxed">
                {analysis.justification_prompt}
              </div>
            )}

            {/* Cabin downgrade suggestion — full width */}
            {hasCabinDowngrade && analysis.cabin_downgrade_suggestion && (
              <div className="mx-5 mb-4 flex items-center justify-between rounded-lg border border-violet-200 bg-violet-50/80 px-4 py-2.5">
                <div className="text-sm text-violet-800">
                  <span className="font-medium">{cabinLabel(analysis.cabin_downgrade_suggestion.suggested_cabin)}</span>
                  {" on the same flights would save "}
                  <span className="font-bold">{formatPrice(analysis.cabin_downgrade_suggestion.savings_amount)}</span>
                  <span className="text-violet-600 text-xs ml-1">
                    ({analysis.cabin_downgrade_suggestion.savings_percent}% less)
                  </span>
                </div>
                {onCabinDowngrade && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-xs shrink-0 ml-3 border-violet-300 text-violet-700 hover:bg-violet-100"
                    onClick={() => onCabinDowngrade(analysis.cabin_downgrade_suggestion!.suggested_cabin)}
                  >
                    Switch to {cabinLabel(analysis.cabin_downgrade_suggestion.suggested_cabin)}
                  </Button>
                )}
              </div>
            )}

            <div className={`grid grid-cols-1 ${hasAlternatives ? "lg:grid-cols-5" : ""} gap-4 px-5`}>
              {/* LEFT COLUMN — Your selections + justification */}
              <div className={`${hasAlternatives ? "lg:col-span-3 lg:sticky lg:top-0 lg:self-start" : ""} space-y-4`}>
                {/* Multi-leg comparison tables */}
                {isMultiLeg ? (
                  <div className="space-y-5">
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
                                {formatPrice(leg.savings.amount)} diff
                              </span>
                            )}
                          </div>
                          {legCheapest && (
                            <ComparisonTable selected={leg.selected} cheapest={legCheapest} />
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <>
                    {cheapestAlt && analysis.selected && (
                      <div className="space-y-2">
                        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                          Comparison
                        </h4>
                        <ComparisonTable selected={analysis.selected} cheapest={cheapestAlt} />
                      </div>
                    )}
                  </>
                )}

                {/* Justification section */}
                <JustificationSection
                  selectedPresets={selectedPresets}
                  togglePreset={togglePreset}
                  justification={justification}
                  setJustification={setJustification}
                  isHighSavings={isHighSavings}
                  canConfirm={canConfirm}
                  fullJustification={fullJustification}
                />

                {/* Actions */}
                <div className="flex justify-end gap-2 pt-2">
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

              {/* RIGHT COLUMN — Alternatives */}
              {hasAlternatives && (
                <div className="lg:col-span-2 space-y-4">
                  {/* Trip-window alternatives — shift entire trip */}
                  {hasTripWindow && (
                    <div className="rounded-lg border border-blue-200 bg-blue-50/30">
                      <div className="px-3 py-2 border-b border-blue-100">
                        <h4 className="text-xs font-semibold uppercase tracking-wide text-blue-700">
                          Shift Your Entire Trip
                        </h4>
                        <p className="text-[10px] text-blue-600 mt-0.5">
                          {analysis.trip_window_alternatives!.original_trip_duration}-day trip (flexible ±2d), different dates
                        </p>
                      </div>
                      {(expandedProposals
                        ? analysis.trip_window_alternatives!.proposals
                        : analysis.trip_window_alternatives!.proposals.slice(0, 3)
                      ).map((proposal, idx) => (
                        <div
                          key={`${proposal.outbound_date}-${proposal.return_date}`}
                          className={`px-3 py-2.5 border-b border-blue-100/50 last:border-b-0 ${idx === 0 ? "bg-emerald-50/30" : ""}`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5 text-xs flex-wrap">
                                {idx === 0 && (
                                  <span className="text-[9px] rounded-full px-1.5 py-0.5 bg-emerald-600 text-white font-semibold">
                                    Top pick
                                  </span>
                                )}
                                <span className="font-medium">{fmtDate(proposal.outbound_date)}</span>
                                <span className="text-muted-foreground">&rarr;</span>
                                <span className="font-medium">{fmtDate(proposal.return_date)}</span>
                                <span className="text-[10px] text-muted-foreground">
                                  ({proposal.trip_duration}d)
                                </span>
                                {analysis.trip_window_alternatives!.original_trip_duration !== proposal.trip_duration && (
                                  <span className="text-[9px] text-amber-600 font-medium">
                                    {proposal.trip_duration > analysis.trip_window_alternatives!.original_trip_duration ? "+" : ""}
                                    {proposal.trip_duration - analysis.trip_window_alternatives!.original_trip_duration}d
                                  </span>
                                )}
                                {proposal.same_airline && proposal.airline_name && (
                                  <span className={`text-[9px] rounded-full px-1.5 py-0.5 ${
                                    proposal.user_airline
                                      ? "bg-primary/10 text-primary font-medium"
                                      : "bg-blue-100 text-blue-700"
                                  }`}>
                                    {proposal.user_airline ? `\u2713 ${proposal.airline_name}` : proposal.airline_name}
                                  </span>
                                )}
                              </div>
                              <div className="text-[10px] text-muted-foreground mt-0.5 space-y-0.5">
                                <div>
                                  Out: {proposal.outbound_flight.airline_name} {formatPrice(proposal.outbound_flight.price)}
                                  {proposal.outbound_flight.stops === 0 ? " (nonstop)" : ` (${proposal.outbound_flight.stops} stop)`}
                                  {fmtTime(proposal.outbound_flight.departure_time) && (
                                    <span className="ml-1">{fmtTime(proposal.outbound_flight.departure_time)} · {fmtDur(proposal.outbound_flight.duration_minutes)}</span>
                                  )}
                                </div>
                                <div>
                                  Ret: {proposal.return_flight.airline_name} {formatPrice(proposal.return_flight.price)}
                                  {proposal.return_flight.stops === 0 ? " (nonstop)" : ` (${proposal.return_flight.stops} stop)`}
                                  {fmtTime(proposal.return_flight.departure_time) && (
                                    <span className="ml-1">{fmtTime(proposal.return_flight.departure_time)} · {fmtDur(proposal.return_flight.duration_minutes)}</span>
                                  )}
                                </div>
                                {proposal.reason && (
                                  <div className="text-[10px] text-blue-600 italic mt-0.5">
                                    {proposal.reason}
                                  </div>
                                )}
                              </div>
                            </div>
                            <div className="text-right shrink-0 ml-2">
                              <div className="text-sm font-bold">{formatPrice(proposal.total_price)}</div>
                              <div className="flex items-center gap-1 justify-end">
                                {proposal.savings > 0 && proposal.savings_percent >= 20 && (
                                  <span className="text-[9px] rounded-full px-1.5 py-0.5 font-medium bg-emerald-100 text-emerald-700">Great deal</span>
                                )}
                                {proposal.savings > 0 && proposal.savings_percent >= 10 && proposal.savings_percent < 20 && (
                                  <span className="text-[9px] rounded-full px-1.5 py-0.5 font-medium bg-amber-100 text-amber-700">Good savings</span>
                                )}
                                <span className={`text-[10px] font-semibold ${
                                  proposal.savings >= 0 ? "text-blue-700" : "text-amber-600"
                                }`}>
                                  {proposal.savings >= 0
                                    ? `Save ${formatPrice(proposal.savings)}`
                                    : `${formatPrice(Math.abs(proposal.savings))} more`
                                  }
                                </span>
                              </div>
                            </div>
                          </div>
                          {onSwitchTripWindow && (
                            <div className="mt-1.5">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => onSwitchTripWindow(proposal)}
                                className="text-xs w-full"
                              >
                                Switch to this option
                              </Button>
                            </div>
                          )}
                        </div>
                      ))}
                      {analysis.trip_window_alternatives!.proposals.length > 3 && (
                        <div className="px-3 py-2">
                          <button
                            onClick={() => setExpandedProposals(!expandedProposals)}
                            className="w-full text-xs text-blue-600 hover:text-blue-800 font-medium py-1 rounded-md hover:bg-blue-50 transition-colors"
                          >
                            {expandedProposals ? "Show less" : `Show ${analysis.trip_window_alternatives!.proposals.length - 3} more options`}
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Different month alternatives — significant date shifts */}
                  {hasDifferentMonth && analysis.trip_window_alternatives?.different_month && (
                    <div className="rounded-lg border border-purple-200 bg-purple-50/30">
                      <div className="px-3 py-2 border-b border-purple-100">
                        <h4 className="text-xs font-semibold uppercase tracking-wide text-purple-700">
                          Consider a Different Month
                        </h4>
                        <p className="text-[10px] text-purple-600 mt-0.5">
                          Your airline on significantly different dates
                        </p>
                      </div>
                      {(expandedDiffMonth
                        ? analysis.trip_window_alternatives.different_month
                        : analysis.trip_window_alternatives.different_month.slice(0, 3)
                      ).map((proposal, idx) => (
                        <div
                          key={`dm-${proposal.outbound_date}-${proposal.return_date}`}
                          className={`px-3 py-2.5 border-b border-purple-100/50 last:border-b-0 ${idx === 0 ? "bg-emerald-50/30" : ""}`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5 text-xs flex-wrap">
                                {idx === 0 && (
                                  <span className="text-[9px] rounded-full px-1.5 py-0.5 bg-emerald-600 text-white font-semibold">
                                    Top pick
                                  </span>
                                )}
                                <span className="font-medium">{fmtDate(proposal.outbound_date)}</span>
                                <span className="text-muted-foreground">&rarr;</span>
                                <span className="font-medium">{fmtDate(proposal.return_date)}</span>
                                <span className="text-[10px] text-muted-foreground">
                                  ({proposal.trip_duration}d)
                                </span>
                                {analysis.trip_window_alternatives!.original_trip_duration !== proposal.trip_duration && (
                                  <span className="text-[9px] text-amber-600 font-medium">
                                    {proposal.trip_duration > analysis.trip_window_alternatives!.original_trip_duration ? "+" : ""}
                                    {proposal.trip_duration - analysis.trip_window_alternatives!.original_trip_duration}d
                                  </span>
                                )}
                                {proposal.same_airline && proposal.airline_name && (
                                  <span className={`text-[9px] rounded-full px-1.5 py-0.5 ${
                                    proposal.user_airline
                                      ? "bg-primary/10 text-primary font-medium"
                                      : "bg-purple-100 text-purple-700"
                                  }`}>
                                    {proposal.user_airline ? `\u2713 ${proposal.airline_name}` : proposal.airline_name}
                                  </span>
                                )}
                              </div>
                              <div className="text-[10px] text-muted-foreground mt-0.5 space-y-0.5">
                                <div>
                                  Out: {proposal.outbound_flight.airline_name} {formatPrice(proposal.outbound_flight.price)}
                                  {proposal.outbound_flight.stops === 0 ? " (nonstop)" : ` (${proposal.outbound_flight.stops} stop)`}
                                  {fmtTime(proposal.outbound_flight.departure_time) && (
                                    <span className="ml-1">{fmtTime(proposal.outbound_flight.departure_time)} · {fmtDur(proposal.outbound_flight.duration_minutes)}</span>
                                  )}
                                </div>
                                <div>
                                  Ret: {proposal.return_flight.airline_name} {formatPrice(proposal.return_flight.price)}
                                  {proposal.return_flight.stops === 0 ? " (nonstop)" : ` (${proposal.return_flight.stops} stop)`}
                                  {fmtTime(proposal.return_flight.departure_time) && (
                                    <span className="ml-1">{fmtTime(proposal.return_flight.departure_time)} · {fmtDur(proposal.return_flight.duration_minutes)}</span>
                                  )}
                                </div>
                                {proposal.reason && (
                                  <div className="text-[10px] text-purple-600 italic mt-0.5">
                                    {proposal.reason}
                                  </div>
                                )}
                              </div>
                            </div>
                            <div className="text-right shrink-0 ml-2">
                              <div className="text-sm font-bold">{formatPrice(proposal.total_price)}</div>
                              <div className="flex items-center gap-1 justify-end">
                                {proposal.savings > 0 && proposal.savings_percent >= 20 && (
                                  <span className="text-[9px] rounded-full px-1.5 py-0.5 font-medium bg-emerald-100 text-emerald-700">Great deal</span>
                                )}
                                {proposal.savings > 0 && proposal.savings_percent >= 10 && proposal.savings_percent < 20 && (
                                  <span className="text-[9px] rounded-full px-1.5 py-0.5 font-medium bg-amber-100 text-amber-700">Good savings</span>
                                )}
                                <span className={`text-[10px] font-semibold ${
                                  proposal.savings >= 0 ? "text-purple-700" : "text-amber-600"
                                }`}>
                                  {proposal.savings >= 0
                                    ? `Save ${formatPrice(proposal.savings)}`
                                    : `${formatPrice(Math.abs(proposal.savings))} more`
                                  }
                                </span>
                              </div>
                            </div>
                          </div>
                          {onSwitchTripWindow && (
                            <div className="mt-1.5">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => onSwitchTripWindow(proposal)}
                                className="text-xs w-full"
                              >
                                Switch to this option
                              </Button>
                            </div>
                          )}
                        </div>
                      ))}
                      {analysis.trip_window_alternatives.different_month.length > 3 && (
                        <div className="px-3 py-2">
                          <button
                            onClick={() => setExpandedDiffMonth(!expandedDiffMonth)}
                            className="w-full text-xs text-purple-600 hover:text-purple-800 font-medium py-1 rounded-md hover:bg-purple-50 transition-colors"
                          >
                            {expandedDiffMonth ? "Show less" : `Show ${analysis.trip_window_alternatives.different_month.length - 3} more options`}
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Per-leg same-day alternatives */}
                  {isMultiLeg ? (
                    <>
                      {analysis.legs!.map((leg) => {
                        if (leg.alternatives.length === 0) return null;
                        const visibleAlts = expandedSameDay ? leg.alternatives : leg.alternatives.slice(0, 2);
                        const selectedPrice = leg.selected?.price || 1;
                        return (
                          <div key={`alt-${leg.leg_id}`} className="space-y-1.5">
                            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                              {leg.route} alternatives
                            </h4>
                            {visibleAlts.map((alt, altIdx) => {
                              const savingsPct = selectedPrice > 0 ? (alt.savings / selectedPrice) * 100 : 0;
                              const isTopPick = altIdx === 0;
                              return (
                                <div
                                  key={alt.flight_option_id}
                                  className={`flex items-center justify-between rounded-lg border px-3 py-2 transition-colors ${
                                    isTopPick ? "border-emerald-200 bg-emerald-50/30 hover:bg-emerald-50/50" : "border-border bg-muted/20 hover:bg-muted/40"
                                  }`}
                                >
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-1.5">
                                      {isTopPick && (
                                        <span className="text-[9px] rounded-full px-1.5 py-0.5 bg-emerald-600 text-white font-semibold">
                                          Top pick
                                        </span>
                                      )}
                                      <span className="text-sm font-medium">{alt.airline}</span>
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                      {alt.label} &middot; {fmtDate(alt.date)}
                                      {fmtTime(alt.departure_time) && (
                                        <> &middot; {fmtTime(alt.departure_time)}</>
                                      )}
                                      {" "}&middot;{" "}
                                      {alt.stops === 0
                                        ? "Nonstop"
                                        : `${alt.stops} stop${alt.stops > 1 ? "s" : ""}`}
                                      {alt.duration_minutes > 0 &&
                                        ` \u00b7 ${fmtDuration(alt.duration_minutes)}`}
                                    </div>
                                    {alt.reason && (
                                      <div className="text-[10px] text-blue-600 italic mt-0.5">
                                        {alt.reason}
                                      </div>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-2 shrink-0">
                                    <div className="text-right">
                                      <div className="flex items-center gap-1 justify-end">
                                        {savingsPct >= 20 && (
                                          <span className="text-[9px] rounded-full px-1.5 py-0.5 font-medium bg-emerald-100 text-emerald-700">Great deal</span>
                                        )}
                                        {savingsPct >= 10 && savingsPct < 20 && (
                                          <span className="text-[9px] rounded-full px-1.5 py-0.5 font-medium bg-amber-100 text-amber-700">Good savings</span>
                                        )}
                                        <span className="text-sm font-bold text-emerald-700">
                                          {formatPrice(alt.price)}
                                        </span>
                                      </div>
                                      <div className="text-[10px] text-emerald-600">
                                        {formatPrice(alt.savings)} less
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
                              );
                            })}
                          </div>
                        );
                      })}
                      {(() => {
                        const hiddenCount = analysis.legs!.reduce(
                          (sum, leg) => sum + Math.max(0, leg.alternatives.length - 2), 0
                        );
                        if (hiddenCount <= 0) return null;
                        return (
                          <button
                            onClick={() => setExpandedSameDay(!expandedSameDay)}
                            className="w-full text-xs text-muted-foreground hover:text-foreground font-medium py-1.5 rounded-md hover:bg-muted/50 transition-colors"
                          >
                            {expandedSameDay ? "Show less" : `Show ${hiddenCount} more alternative${hiddenCount > 1 ? "s" : ""}`}
                          </button>
                        );
                      })()}
                    </>
                  ) : (
                    analysis.alternatives && analysis.alternatives.length > 0 && (
                      <div className="space-y-1.5">
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
                                {alt.label} &middot; {fmtDate(alt.date)}
                                {fmtTime(alt.departure_time) && (
                                  <> &middot; {fmtTime(alt.departure_time)}</>
                                )}
                                {" "}&middot;{" "}
                                {alt.stops === 0
                                  ? "Nonstop"
                                  : `${alt.stops} stop${alt.stops > 1 ? "s" : ""}`}
                                {alt.duration_minutes > 0 &&
                                  ` \u00b7 ${fmtDuration(alt.duration_minutes)}`}
                              </div>
                              {alt.reason && (
                                <div className="text-[10px] text-blue-600 italic mt-0.5">
                                  {alt.reason}
                                </div>
                              )}
                            </div>
                            <div className="flex items-center gap-3">
                              <div className="text-right">
                                <div className="text-sm font-bold text-emerald-700">
                                  {formatPrice(alt.price)}
                                </div>
                                <div className="text-[10px] text-emerald-600">
                                  save {formatPrice(alt.savings)}
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
                    )
                  )}

                </div>
              )}
            </div>

            {/* Sticky bottom action bar */}
            <div className="sticky bottom-0 bg-card border-t border-border px-5 py-3 flex items-center justify-between">
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
          </>
        )}
      </div>
    </div>
  );
}
