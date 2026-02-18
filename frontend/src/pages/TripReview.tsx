import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import apiClient from "@/api/client";
import { useTripStore } from "@/stores/tripStore";
import { ExportButton } from "@/components/shared/ExportButton";
import { formatPrice } from "@/lib/currency";

interface EvalResult {
  savings_report: {
    currency: string;
    selected_total: number;
    cheapest_total: number;
    most_expensive_total: number;
    savings_vs_expensive: number;
    premium_vs_cheapest: number;
    narrative: string;
    policy_status: string;
    policy_checks: Array<{
      policy_name: string;
      status: string;
      details: string;
    }>;
    per_leg_summary: Array<{
      leg_id: string;
      route: string;
      selected_price: number;
      cheapest_price: number;
    }>;
    hotel_selected_total: number | null;
    hotel_cheapest_total: number | null;
    events_context: string[] | null;
  } | null;
  warnings: Array<{
    policy_name: string;
    message: string;
    policy_id?: string;
    requires_justification?: boolean;
  }>;
  blocks: Array<{
    policy_name: string;
    message: string;
    policy_id: string;
  }>;
  error?: string;
}

const statusIcons: Record<string, string> = {
  pass: "✓",
  warn: "⚠",
  block: "✕",
  info: "ℹ",
};

const statusColors: Record<string, string> = {
  pass: "text-green-600",
  warn: "text-amber-600",
  block: "text-red-600",
  info: "text-blue-600",
};

export default function TripReview() {
  const { tripId } = useParams<{ tripId: string }>();
  const navigate = useNavigate();
  const { currentTrip, fetchTrip } = useTripStore();
  const [evalResult, setEvalResult] = useState<EvalResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [notes, setNotes] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [violationAcks, setViolationAcks] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (tripId) {
      fetchTrip(tripId);
      apiClient
        .post(`/trips/${tripId}/evaluate`)
        .then((res) => setEvalResult(res.data))
        .catch((err) => {
          setEvalResult({
            savings_report: null,
            warnings: [],
            blocks: [],
            error: err.response?.data?.detail || "Failed to evaluate trip",
          });
        })
        .finally(() => setLoading(false));
    }
  }, [tripId, fetchTrip]);

  const handleSubmit = async () => {
    if (!tripId) return;
    setSubmitting(true);
    try {
      // Build violation justifications — single acknowledgment covers all
      const justifications: Record<string, string> = {};
      const ackNote = notes || "Acknowledged";
      for (const b of evalResult?.blocks || []) {
        if (b.policy_id && violationAcks[b.policy_id]) {
          justifications[b.policy_id] = ackNote;
        }
      }
      for (const w of evalResult?.warnings || []) {
        if (w.policy_id && w.requires_justification && violationAcks[w.policy_id]) {
          justifications[w.policy_id] = ackNote;
        }
      }

      await apiClient.post(`/trips/${tripId}/submit`, {
        traveler_notes: notes || undefined,
        violation_justifications: Object.keys(justifications).length > 0 ? justifications : undefined,
      });
      setSubmitted(true);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      alert(error.response?.data?.detail || "Submission failed");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-64 bg-muted animate-pulse rounded" />
        <div className="h-72 bg-muted animate-pulse rounded-lg" />
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="text-center py-16 space-y-4">
        <div className="text-5xl">✓</div>
        <h2 className="text-2xl font-bold">Trip Submitted!</h2>
        <p className="text-muted-foreground">
          Your trip has been submitted for approval. You&apos;ll be notified when
          your manager reviews it.
        </p>
        <div className="flex gap-3 justify-center">
          <Button onClick={() => navigate("/trips")}>View My Trips</Button>
          <Button variant="outline" onClick={() => navigate("/")}>
            Dashboard
          </Button>
        </div>
      </div>
    );
  }

  const sr = evalResult?.savings_report;
  const hasBlocks = (evalResult?.blocks?.length || 0) > 0;

  // Combine blocks + warnings that need justification into one list
  const allViolations = [
    ...(evalResult?.blocks || []).map((b) => ({ ...b, message: b.message, requires_justification: true })),
    ...(evalResult?.warnings || []).filter((w) => w.requires_justification),
  ];
  const unackedCount = allViolations.filter(
    (v) => v.policy_id && !violationAcks[v.policy_id]
  ).length;
  const allViolationsAcked = unackedCount === 0;
  const isReadOnly = currentTrip?.status && !["draft", "searching", "changes_requested"].includes(currentTrip.status);

  return (
    <div className="space-y-6">
      <div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate(-1)}
          className="mb-2"
        >
          &larr; Back
        </Button>
        <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold tracking-tight">
          Review & Submit
        </h2>
        {tripId && (
          <div className="flex gap-2">
            <ExportButton tripId={tripId} type="savings" />
            <ExportButton tripId={tripId} type="audit" />
          </div>
        )}
        </div>
        <p className="text-muted-foreground mt-1">
          Review your trip details and savings before submitting for approval.
        </p>
      </div>

      {/* Trip Info */}
      {currentTrip && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">
              {currentTrip.title || "Untitled Trip"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {currentTrip.legs.map((leg) => (
                <div
                  key={leg.id}
                  className="flex items-center justify-between py-2 border-b last:border-0"
                >
                  <span className="font-medium">
                    {leg.origin_airport} → {leg.destination_airport}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {leg.preferred_date} · {leg.cabin_class}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error */}
      {evalResult?.error && (
        <Card className="border-amber-200">
          <CardContent className="pt-6">
            <p className="text-amber-700">{evalResult.error}</p>
          </CardContent>
        </Card>
      )}

      {/* Savings Card */}
      {sr && (
        <Card>
          <CardContent className="pt-6 space-y-4">
            <div className="flex items-baseline justify-between">
              <span className="text-3xl font-bold">
                {formatPrice(sr.selected_total, sr.currency)}
              </span>
              <span
                className={`px-3 py-1 rounded-full text-sm font-medium ${
                  sr.policy_status === "compliant"
                    ? "bg-green-100 text-green-800"
                    : sr.policy_status === "warning"
                    ? "bg-amber-100 text-amber-800"
                    : "bg-blue-100 text-blue-800"
                }`}
              >
                {sr.policy_status === "compliant"
                  ? "Compliant"
                  : sr.policy_status === "warning"
                  ? "Items to Review"
                  : "Items to Review"}
              </span>
            </div>

            {/* Cost Bar */}
            <div className="relative h-6 bg-muted rounded-full overflow-visible">
              {/* Green zone: 0 → cheapest */}
              <div
                className="absolute h-full bg-green-200 rounded-l-full"
                style={{
                  width: `${
                    (sr.cheapest_total / sr.most_expensive_total) * 100
                  }%`,
                }}
              />
              {/* Amber zone: cheapest → selected (premium over cheapest) */}
              {sr.selected_total > sr.cheapest_total && (
                <div
                  className="absolute h-full bg-amber-200"
                  style={{
                    left: `${
                      (sr.cheapest_total / sr.most_expensive_total) * 100
                    }%`,
                    width: `${
                      ((sr.selected_total - sr.cheapest_total) / sr.most_expensive_total) * 100
                    }%`,
                  }}
                />
              )}
              {/* Selected price indicator */}
              <div
                className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-5 h-5 rounded-full bg-primary border-2 border-white shadow-md z-10"
                style={{
                  left: `${
                    (sr.selected_total / sr.most_expensive_total) * 100
                  }%`,
                }}
              />
            </div>
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Cheapest: {formatPrice(sr.cheapest_total, sr.currency)}</span>
              <span className="font-medium text-foreground">Selected: {formatPrice(sr.selected_total, sr.currency)}</span>
              <span>Expensive: {formatPrice(sr.most_expensive_total, sr.currency)}</span>
            </div>

            {/* Narrative */}
            <div className="bg-blue-50 rounded-lg p-4">
              <p className="text-sm leading-relaxed">{sr.narrative}</p>
            </div>

            {/* Savings */}
            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-3 bg-green-50 rounded-lg">
                <p className="text-2xl font-bold text-green-700">
                  {formatPrice(sr.savings_vs_expensive, sr.currency)}
                </p>
                <p className="text-xs text-green-600">
                  Saved vs. expensive
                </p>
              </div>
              <div className="text-center p-3 bg-amber-50 rounded-lg">
                <p className="text-2xl font-bold text-amber-700">
                  {formatPrice(sr.premium_vs_cheapest, sr.currency)}
                </p>
                <p className="text-xs text-amber-600">
                  Above lowest fare
                </p>
              </div>
            </div>

            {/* Hotel Costs */}
            {sr.hotel_selected_total != null && (
              <div className="p-3 bg-indigo-50 rounded-lg">
                <h4 className="text-sm font-semibold mb-1">Hotel</h4>
                <div className="flex items-baseline gap-3">
                  <span className="text-lg font-bold text-indigo-700">
                    {formatPrice(sr.hotel_selected_total, sr.currency)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Combined total: {formatPrice(sr.selected_total + sr.hotel_selected_total, sr.currency)}
                  </span>
                </div>
              </div>
            )}

            {/* Event Context */}
            {sr.events_context && sr.events_context.length > 0 && (
              <div className="p-3 bg-orange-50 rounded-lg">
                <h4 className="text-sm font-semibold mb-1">
                  Events Affecting Price
                </h4>
                <ul className="text-xs text-muted-foreground space-y-0.5">
                  {sr.events_context.map((ctx, i) => (
                    <li key={i}>{ctx}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Policy Checks */}
            <div>
              <h4 className="text-sm font-semibold mb-2">Policy Checks</h4>
              <div className="space-y-1">
                {sr.policy_checks.map((check, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between text-sm py-1"
                  >
                    <div className="flex items-center gap-2">
                      <span className={statusColors[check.status] || ""}>
                        {statusIcons[check.status] || "•"}
                      </span>
                      <span>{check.policy_name}</span>
                    </div>
                    <span className="text-muted-foreground text-xs">
                      {check.details}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Per-leg breakdown */}
            {sr.per_leg_summary.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold mb-2">
                  Per-Leg Summary
                </h4>
                {sr.per_leg_summary.map((leg, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between text-sm py-1 border-b last:border-0"
                  >
                    <span className="font-medium">{leg.route}</span>
                    <span className="text-muted-foreground">
                      {formatPrice(leg.selected_price, sr.currency)} (cheapest: {formatPrice(leg.cheapest_price, sr.currency)})
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Policy Warnings (blocks + warnings that need acknowledgment) */}
      {allViolations.length > 0 && (
        <Card className="border-blue-200">
          <CardContent className="pt-6 space-y-3">
            <h4 className="text-sm font-semibold text-blue-700 mb-2">
              Policy Notes
            </h4>
            {allViolations.map((v, i) => (
              <div key={i} className="rounded-md border border-blue-200 bg-blue-50/50 p-3">
                <p className="text-sm text-blue-800">
                  <span className="font-medium">{v.policy_name}:</span> {v.message}
                </p>
              </div>
            ))}
            {/* Single acknowledgment for all policy notes */}
            <div className="rounded-md border border-blue-300 bg-blue-50 p-3 space-y-2">
              <div className="flex items-start gap-2">
                <input
                  type="checkbox"
                  id="ack-all"
                  checked={allViolationsAcked}
                  onChange={(e) => {
                    const acks: Record<string, boolean> = {};
                    for (const v of allViolations) {
                      if (v.policy_id) acks[v.policy_id] = e.target.checked;
                    }
                    setViolationAcks(acks);
                  }}
                  className="mt-0.5"
                />
                <label htmlFor="ack-all" className="text-sm text-blue-800 font-medium">
                  I acknowledge {allViolations.length === 1 ? "this policy note" : `all ${allViolations.length} policy notes`}
                </label>
              </div>
              {allViolationsAcked && (
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Brief context for your approver (optional)..."
                  className="w-full rounded-md border border-blue-200 bg-white px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300/50"
                />
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Notes & Submit */}
      {sr && !isReadOnly && (
        <Card>
          <CardContent className="pt-6 space-y-3">
            <textarea
              className="w-full border rounded-md px-3 py-2 text-sm bg-background"
              placeholder="Add notes for your approver (optional)..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
            />
            <div className="flex gap-3">
              <Button
                onClick={handleSubmit}
                disabled={submitting || (allViolations.length > 0 && !allViolationsAcked)}
                className="w-full"
              >
                {submitting
                  ? "Submitting..."
                  : allViolations.length > 0 && !allViolationsAcked
                  ? `Acknowledge ${unackedCount} policy note${unackedCount > 1 ? "s" : ""} above to submit`
                  : "Submit for Approval"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Read-only status for submitted trips */}
      {isReadOnly && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                currentTrip?.status === "approved" ? "bg-green-100 text-green-800"
                  : currentTrip?.status === "rejected" ? "bg-red-100 text-red-800"
                  : "bg-blue-100 text-blue-800"
              }`}>
                {currentTrip?.status === "submitted" ? "Submitted — Pending Approval"
                  : currentTrip?.status === "approved" ? "Approved"
                  : currentTrip?.status === "rejected" ? "Rejected"
                  : currentTrip?.status || "Unknown"}
              </span>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
