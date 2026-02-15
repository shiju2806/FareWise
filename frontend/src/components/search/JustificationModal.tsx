import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { FlightOption } from "@/types/flight";

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
}

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

export function JustificationModal({
  analysis,
  onConfirm,
  onSwitch,
  onCancel,
  confirming = false,
}: Props) {
  const [justification, setJustification] = useState("");

  const canConfirm = justification.trim().length >= 10;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onCancel}
      />

      {/* Modal */}
      <div className="relative bg-card rounded-xl shadow-2xl border border-border max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="px-5 pt-5 pb-3">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="text-base font-semibold">
                Cheaper Options Available
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                {analysis.selected.airline} on {fmtDate(analysis.selected.date)}{" "}
                at {fmtPrice(analysis.selected.price)}
              </p>
            </div>
            <span className="inline-flex items-center rounded-md bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-800">
              Save up to {fmtPrice(analysis.savings.amount)} (
              {analysis.savings.percent}%)
            </span>
          </div>
        </div>

        {/* LLM prompt */}
        {analysis.justification_prompt && (
          <div className="mx-5 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
            {analysis.justification_prompt}
          </div>
        )}

        {/* Alternatives */}
        {analysis.alternatives.length > 0 && (
          <div className="px-5 pt-4 space-y-2">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Alternatives
            </h4>
            {analysis.alternatives.map((alt) => (
              <div
                key={alt.flight_option_id}
                className="flex items-center justify-between rounded-lg border border-border bg-muted/30 px-3 py-2.5"
              >
                <div>
                  <div className="text-sm font-medium">{alt.airline}</div>
                  <div className="text-xs text-muted-foreground">
                    {alt.label} &middot; {fmtDate(alt.date)} &middot;{" "}
                    {alt.stops === 0
                      ? "Nonstop"
                      : `${alt.stops} stop${alt.stops > 1 ? "s" : ""}`}
                    {alt.duration_minutes > 0 &&
                      ` \u00B7 ${Math.floor(alt.duration_minutes / 60)}h ${alt.duration_minutes % 60}m`}
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

        {/* Justification textarea */}
        <div className="px-5 pt-4 space-y-1.5">
          <label
            htmlFor="justification"
            className="text-xs font-semibold text-muted-foreground uppercase tracking-wide"
          >
            Why this flight?
          </label>
          <textarea
            id="justification"
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
            placeholder="e.g., Schedule alignment with meeting, loyalty program preference, nonstop requirement..."
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm min-h-[80px] resize-y focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          <p className="text-[10px] text-muted-foreground">
            {justification.trim().length < 10
              ? `At least 10 characters required (${justification.trim().length}/10)`
              : "This note will be included with your travel request"}
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
            onClick={() => onConfirm(justification.trim())}
          >
            {confirming ? "Saving..." : "Confirm Selection"}
          </Button>
        </div>
      </div>
    </div>
  );
}
