import { useState } from "react";
import { Button } from "@/components/ui/button";

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
}

interface AnalysisResult {
  justification_required: boolean;
  selected: {
    airline: string;
    date: string;
    price: number;
    stops: number;
    duration_minutes: number;
    flight_option_id: string;
  };
  savings: {
    amount: number;
    percent: number;
  };
  alternatives: Alternative[];
  justification_prompt: string | null;
}

interface Props {
  analysis: AnalysisResult;
  onConfirm: (justification: string) => void;
  onSwitch: (flightOptionId: string) => void;
  onCancel: () => void;
  confirming?: boolean;
  /** "inline" renders as a banner (for $100-500), "modal" renders full overlay (for >$500) */
  mode?: "inline" | "modal";
}

const PRESETS = [
  "Schedule alignment with meetings",
  "Loyalty program / status",
  "Nonstop preference",
  "Client / customer requirement",
  "Personal safety / comfort",
];

function fmtPrice(price: number): string {
  return `$${Math.round(price).toLocaleString()}`;
}

function fmtDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    weekday: "short",
  });
}

function fmtDuration(minutes: number): string {
  if (!minutes) return "—";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h ${m}m`;
}

function savingsColor(amount: number): string {
  if (amount >= 500) return "bg-red-100 text-red-800 border-red-200";
  if (amount >= 200) return "bg-amber-100 text-amber-800 border-amber-200";
  return "bg-emerald-100 text-emerald-800 border-emerald-200";
}

/** Comparison table — Selected vs Cheapest alternative */
function ComparisonTable({
  selected,
  cheapest,
}: {
  selected: AnalysisResult["selected"];
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
            <th className="text-center px-3 py-1.5 font-semibold text-emerald-700">Cheapest</th>
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
  const isHighSavings = analysis.savings.amount >= 500;
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

  const cheapestAlt = analysis.alternatives[0];

  // ---- Inline banner mode (for $100-$500) ----
  if (mode === "inline") {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold ${savingsColor(analysis.savings.amount)}`}>
              {fmtPrice(analysis.savings.amount)} cheaper option available
            </span>
            <span className="text-xs text-muted-foreground">
              {cheapestAlt?.airline} at {cheapestAlt ? fmtPrice(cheapestAlt.price) : "—"}
            </span>
          </div>
          {cheapestAlt && (
            <Button
              size="sm"
              variant="outline"
              className="text-xs h-7"
              onClick={() => onSwitch(cheapestAlt.flight_option_id)}
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
            {canConfirm ? "Click confirm to proceed" : "Select a reason to continue"}
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
              <h3 className="text-base font-semibold">Cheaper Options Available</h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                {analysis.selected.airline} on {fmtDate(analysis.selected.date)}{" "}
                at {fmtPrice(analysis.selected.price)}
              </p>
            </div>
            <span className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold ${savingsColor(analysis.savings.amount)}`}>
              Save {fmtPrice(analysis.savings.amount)} ({analysis.savings.percent}%)
            </span>
          </div>
        </div>

        {/* LLM prompt */}
        {analysis.justification_prompt && (
          <div className="mx-5 rounded-lg border border-blue-200 bg-blue-50/80 p-3 text-sm text-blue-800 leading-relaxed">
            {analysis.justification_prompt}
          </div>
        )}

        {/* Side-by-side comparison */}
        {cheapestAlt && (
          <div className="px-5 pt-4">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
              Comparison
            </h4>
            <ComparisonTable selected={analysis.selected} cheapest={cheapestAlt} />
          </div>
        )}

        {/* Alternative cards */}
        {analysis.alternatives.length > 0 && (
          <div className="px-5 pt-4 space-y-2">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Switch to a cheaper option
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

        {/* Quick-justify presets */}
        <div className="px-5 pt-4 space-y-2">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Why this flight?
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
            placeholder={selectedPresets.size > 0 ? "Add any additional context (optional)..." : "Type a custom justification..."}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm min-h-[60px] resize-y focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          <p className="text-[10px] text-muted-foreground">
            {isHighSavings && fullJustification.length < 10
              ? `Justification required for savings over $500 (${fullJustification.length}/10 chars)`
              : canConfirm
              ? "This note will be included with your travel request"
              : "Select a reason above or type a custom justification"}
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
