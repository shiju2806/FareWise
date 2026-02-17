import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import apiClient from "@/api/client";

interface PolicyCheck {
  policy_name: string;
  status: string;
  details: string;
}

interface Warning {
  policy_name: string;
  message: string;
  policy_id?: string;
  requires_justification?: boolean;
}

interface Block {
  policy_name: string;
  message: string;
  policy_id: string;
}

interface LegSummary {
  leg_id: string;
  route: string;
  selected_price: number;
  cheapest_price: number;
}

export interface EvalResult {
  savings_report: {
    selected_total: number;
    cheapest_total: number;
    policy_status: string;
    policy_checks: PolicyCheck[];
    per_leg_summary: LegSummary[];
    narrative: string;
  } | null;
  warnings: Warning[];
  blocks: Block[];
  error?: string;
}

interface SelectedFlight {
  id: string;
  airline_name: string;
  price: number;
  origin_airport: string;
  destination_airport: string;
}

interface InlineReviewPanelProps {
  tripId: string;
  evalResult: EvalResult;
  selectedFlights: Record<string, SelectedFlight>;
  legs: Array<{ id: string; origin_airport: string; destination_airport: string }>;
  onSubmitSuccess: () => void;
  onCancel: () => void;
}

const statusIcons: Record<string, string> = {
  pass: "\u2713",
  warn: "\u26A0",
  block: "\u2715",
  info: "\u2139",
};

const statusColors: Record<string, string> = {
  pass: "text-green-600",
  warn: "text-amber-600",
  block: "text-red-600",
  info: "text-blue-600",
};

export function InlineReviewPanel({
  tripId,
  evalResult,
  selectedFlights,
  legs,
  onSubmitSuccess,
  onCancel,
}: InlineReviewPanelProps) {
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [violationAcks, setViolationAcks] = useState<Record<string, boolean>>({});
  const [violationNotes, setViolationNotes] = useState<Record<string, string>>({});

  const sr = evalResult.savings_report;

  // Combine blocks + warnings needing justification
  const allViolations = [
    ...(evalResult.blocks || []).map((b) => ({
      ...b,
      requires_justification: true as const,
    })),
    ...(evalResult.warnings || []).filter((w) => w.requires_justification),
  ];
  const allViolationsAcked = allViolations.every(
    (v) => !v.policy_id || violationAcks[v.policy_id!]
  );

  async function handleSubmit() {
    setSubmitting(true);
    try {
      const justifications: Record<string, string> = {};
      for (const v of allViolations) {
        if (v.policy_id && violationAcks[v.policy_id]) {
          justifications[v.policy_id] = violationNotes[v.policy_id] || "Acknowledged";
        }
      }

      await apiClient.post(`/trips/${tripId}/submit`, {
        traveler_notes: notes || undefined,
        violation_justifications:
          Object.keys(justifications).length > 0 ? justifications : undefined,
      });
      setSubmitted(true);
      onSubmitSuccess();
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      alert(error.response?.data?.detail || "Submission failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="rounded-lg border border-green-200 bg-green-50/80 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-green-600 text-lg">{"\u2713"}</span>
          <span className="text-sm font-semibold text-green-800">
            Trip submitted for approval!
          </span>
        </div>
        <div className="flex gap-2">
          <Link to="/trips">
            <Button variant="outline" size="sm" className="text-xs">
              View My Trips
            </Button>
          </Link>
          <Link to={`/trips/${tripId}/review`}>
            <Button variant="outline" size="sm" className="text-xs">
              View Details
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-4 shadow-sm">
      <h4 className="text-sm font-semibold">Quick Review & Submit</h4>

      {/* Per-leg summary */}
      <div className="space-y-1">
        {legs.map((leg) => {
          const flight = selectedFlights[leg.id];
          return (
            <div
              key={leg.id}
              className="flex items-center justify-between text-xs py-1"
            >
              <span className="text-muted-foreground">
                {leg.origin_airport} → {leg.destination_airport}
              </span>
              {flight ? (
                <span className="font-medium">
                  {flight.airline_name} · $
                  {Math.round(flight.price).toLocaleString()}
                </span>
              ) : (
                <span className="text-muted-foreground italic">No selection</span>
              )}
            </div>
          );
        })}
        {sr && (
          <div className="flex items-center justify-between text-xs pt-1 border-t border-border">
            <span className="font-medium">Total</span>
            <span className="font-bold">
              ${Math.round(sr.selected_total).toLocaleString()} CAD
            </span>
          </div>
        )}
      </div>

      {/* Policy checks */}
      {sr && sr.policy_checks.length > 0 && (
        <div className="space-y-0.5">
          {sr.policy_checks
            .filter((c) => c.status !== "info" || c.status === "pass")
            .slice(0, 5)
            .map((check, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className={statusColors[check.status] || ""}>
                  {statusIcons[check.status] || "•"}
                </span>
                <span className="text-muted-foreground">{check.policy_name}</span>
              </div>
            ))}
        </div>
      )}

      {/* Policy violations that need acknowledgment */}
      {allViolations.length > 0 && (
        <div className="space-y-2">
          {allViolations.map((v, i) => (
            <div
              key={i}
              className="rounded-md border border-amber-200 bg-amber-50/50 p-2.5 space-y-1.5"
            >
              <p className="text-xs text-amber-800">
                <span className="font-medium">{v.policy_name}:</span> {v.message}
              </p>
              {v.policy_id && (
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id={`inline-ack-${v.policy_id}`}
                    checked={violationAcks[v.policy_id] || false}
                    onChange={(e) =>
                      setViolationAcks((prev) => ({
                        ...prev,
                        [v.policy_id!]: e.target.checked,
                      }))
                    }
                  />
                  <label
                    htmlFor={`inline-ack-${v.policy_id}`}
                    className="text-[11px] text-amber-700"
                  >
                    I acknowledge this exception
                  </label>
                </div>
              )}
              {v.policy_id && violationAcks[v.policy_id] && (
                <input
                  type="text"
                  value={violationNotes[v.policy_id] || ""}
                  onChange={(e) =>
                    setViolationNotes((prev) => ({
                      ...prev,
                      [v.policy_id!]: e.target.value,
                    }))
                  }
                  placeholder="Brief reason (optional)..."
                  className="w-full rounded-md border border-amber-200 bg-white px-2 py-1 text-[11px] focus:outline-none focus:ring-2 focus:ring-amber-300/50"
                />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Notes */}
      <textarea
        className="w-full border rounded-md px-2.5 py-1.5 text-xs bg-background resize-none"
        placeholder="Notes for your approver (optional)..."
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        rows={2}
      />

      {/* Actions */}
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" className="text-xs" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          size="sm"
          className="text-xs"
          disabled={
            submitting ||
            (allViolations.length > 0 && !allViolationsAcked)
          }
          onClick={handleSubmit}
        >
          {submitting
            ? "Submitting..."
            : allViolations.length > 0 && !allViolationsAcked
            ? "Acknowledge warnings"
            : "Submit to Manager"}
        </Button>
      </div>
    </div>
  );
}
