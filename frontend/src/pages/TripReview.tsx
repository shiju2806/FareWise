import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import apiClient from "@/api/client";
import { useTripStore } from "@/stores/tripStore";
import { ExportButton } from "@/components/shared/ExportButton";
import { formatPrice } from "@/lib/currency";
import { formatShortDate } from "@/lib/dates";
import { statusIcons, statusColors } from "@/lib/policy";
import { TripWindowCard } from "@/components/trip/TripWindowCard";
import { CostSpectrumBar } from "@/components/trip/CostSpectrumBar";
import type { EvalResult, ReviewAnalysis } from "@/types/evaluation";

export default function TripReview() {
  const { tripId } = useParams<{ tripId: string }>();
  const navigate = useNavigate();
  const { currentTrip, fetchTrip } = useTripStore();
  const [evalResult, setEvalResult] = useState<EvalResult | null>(null);
  const [analysis, setAnalysis] = useState<ReviewAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [notes, setNotes] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [violationAcks, setViolationAcks] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!tripId) return;
    fetchTrip(tripId);

    apiClient
      .post(`/trips/${tripId}/evaluate`)
      .then(async (res) => {
        setEvalResult(res.data);

        // Prefer persisted snapshot (saved at confirmation time)
        if (res.data.analysis_snapshot) {
          setAnalysis({
            legs: res.data.analysis_snapshot.legs || [],
            trip_totals: res.data.analysis_snapshot.trip_totals,
            trip_window_alternatives: res.data.analysis_snapshot.trip_window_alternatives,
          });
        } else {
          // Fallback: live fetch for trips without snapshot
          const selectedFlights = res.data.selected_flights;
          if (selectedFlights && Object.keys(selectedFlights).length > 0) {
            setAnalysisLoading(true);
            try {
              const analysisRes = await apiClient.post(
                `/trips/${tripId}/analyze-selections`,
                { selected_flights: selectedFlights }
              );
              setAnalysis(analysisRes.data);
            } catch {
              // Alternatives are optional — page works without them
            }
            setAnalysisLoading(false);
          }
        }
      })
      .catch((err) => {
        setEvalResult({
          savings_report: null,
          warnings: [],
          blocks: [],
          error: err.response?.data?.detail || "Failed to evaluate trip",
        });
      })
      .finally(() => setLoading(false));
  }, [tripId, fetchTrip]);

  const handleSubmit = async () => {
    if (!tripId) return;
    setSubmitting(true);
    try {
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
      setTimeout(() => navigate("/trips"), 2000);
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
        </div>
      </div>
    );
  }

  const sr = evalResult?.savings_report;

  const allViolations = [
    ...(evalResult?.blocks || []).map((b) => ({ ...b, message: b.message, requires_justification: true })),
    ...(evalResult?.warnings || []).filter((w) => w.requires_justification),
  ];
  const unackedCount = allViolations.filter(
    (v) => v.policy_id && !violationAcks[v.policy_id]
  ).length;
  const allViolationsAcked = unackedCount === 0;
  const isReadOnly = currentTrip?.status && !["draft", "searching", "changes_requested"].includes(currentTrip.status);

  // Alternatives data
  const tripWindow = analysis?.trip_window_alternatives;
  const hasAlternatives = !!(
    (tripWindow && tripWindow.proposals.length > 0) ||
    (tripWindow?.different_month && tripWindow.different_month.length > 0) ||
    analysis?.legs?.some((l) => l.alternatives.length > 0)
  );

  return (
    <div className="space-y-6">
      {/* Header */}
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
          <h2 className="text-2xl font-bold tracking-tight">Review & Submit</h2>
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

      {/* Error */}
      {evalResult?.error && (
        <Card className="border-amber-200">
          <CardContent className="pt-6">
            <p className="text-amber-700">{evalResult.error}</p>
          </CardContent>
        </Card>
      )}

      {/* 2-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* LEFT COLUMN — Your Selection */}
        <div className={`space-y-4 ${hasAlternatives || analysisLoading ? "lg:col-span-3" : "lg:col-span-5"}`}>
          {/* Trip Info */}
          {currentTrip && (
            <Card>
              <CardHeader className="pb-3">
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
                        {formatShortDate(leg.preferred_date)} · {leg.cabin_class}
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Your Initial Selection (from analysis snapshot) */}
          {analysis?.legs && analysis.legs.length > 0 && analysis.legs.some(l => l.selected) && (
            <Card className="border-primary/30">
              <CardContent className="pt-5 space-y-3">
                <h4 className="text-sm font-semibold">Your Initial Selection</h4>
                {analysis.legs.map((leg, i) => {
                  if (!leg.selected) return null;
                  const tripLeg = currentTrip?.legs.find(l => l.id === leg.leg_id) || currentTrip?.legs[i];
                  const dateChanged = tripLeg && leg.selected.date !== tripLeg.preferred_date;
                  return (
                    <div key={leg.leg_id || i} className="rounded-md border border-border bg-muted/20 px-3 py-2.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-muted-foreground">
                          Leg {leg.sequence || i + 1}: {leg.route}
                        </span>
                        <span className="text-sm font-bold">
                          {formatPrice(leg.selected.price)}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-xs font-medium">{leg.selected.airline}</span>
                        <span className="text-xs text-muted-foreground">
                          {leg.selected.stops === 0 ? "Nonstop" : `${leg.selected.stops} stop${leg.selected.stops > 1 ? "s" : ""}`}
                        </span>
                        <span className="text-xs">{formatShortDate(leg.selected.date)}</span>
                        {dateChanged && tripLeg && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">
                            Changed to {formatShortDate(tripLeg.preferred_date)}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
                {analysis.trip_totals && (
                  <div className="flex items-center justify-between pt-2 border-t">
                    <span className="text-xs font-medium text-muted-foreground">Trip Total</span>
                    <span className="text-sm font-bold">{formatPrice(analysis.trip_totals.selected)}</span>
                  </div>
                )}
                {/* Savings badge — compare original search dates price vs selected */}
                {(() => {
                  const originalPrice = analysis.trip_window_alternatives?.original_total_price;
                  const currentPrice = sr?.selected_total ?? analysis.trip_totals.selected;
                  if (originalPrice && originalPrice > currentPrice) {
                    return (
                      <div className="rounded-md bg-emerald-50 border border-emerald-200 px-3 py-2 text-center">
                        <span className="text-sm font-bold text-emerald-700">
                          Saving the company {formatPrice(originalPrice - currentPrice, sr?.currency)}
                        </span>
                        <span className="text-[10px] text-emerald-600 ml-1">
                          vs original dates ({formatPrice(originalPrice, sr?.currency)})
                        </span>
                      </div>
                    );
                  }
                  return null;
                })()}
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
                        : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {sr.policy_status === "compliant" ? "Compliant" : "Items to Review"}
                  </span>
                </div>

                {/* Cost Bar */}
                <CostSpectrumBar
                  cheapest={sr.cheapest_total}
                  selected={sr.selected_total}
                  mostExpensive={sr.most_expensive_total}
                  currency={sr.currency}
                />

                {/* Narrative */}
                <div className="bg-blue-50 rounded-lg p-4">
                  <p className="text-sm leading-relaxed">{sr.narrative}</p>
                </div>

                {/* Savings Summary */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="text-center p-3 bg-green-50 rounded-lg">
                    <p className="text-2xl font-bold text-green-700">
                      {formatPrice(sr.savings_vs_expensive, sr.currency)}
                    </p>
                    <p className="text-xs text-green-600">Saved vs. expensive</p>
                  </div>
                  <div className="text-center p-3 bg-amber-50 rounded-lg">
                    <p className="text-2xl font-bold text-amber-700">
                      {formatPrice(sr.premium_vs_cheapest, sr.currency)}
                    </p>
                    <p className="text-xs text-amber-600">Above lowest fare</p>
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
                    <h4 className="text-sm font-semibold mb-1">Events Affecting Price</h4>
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
                      <div key={i} className="flex items-center justify-between text-sm py-1">
                        <div className="flex items-center gap-2">
                          <span className={statusColors[check.status] || ""}>
                            {statusIcons[check.status] || "•"}
                          </span>
                          <span>{check.policy_name}</span>
                        </div>
                        <span className="text-muted-foreground text-xs">{check.details}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Per-leg breakdown */}
                {sr.per_leg_summary.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold mb-2">Per-Leg Summary</h4>
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

          {/* Policy Notes + Acknowledgment */}
          {allViolations.length > 0 && (
            <Card className="border-blue-200">
              <CardContent className="pt-6 space-y-3">
                <h4 className="text-sm font-semibold text-blue-700 mb-2">Policy Notes</h4>
                {allViolations.map((v, i) => (
                  <div key={i} className="rounded-md border border-blue-200 bg-blue-50/50 p-3">
                    <p className="text-sm text-blue-800">
                      <span className="font-medium">{v.policy_name}:</span> {v.message}
                    </p>
                  </div>
                ))}
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

          {/* Read-only status */}
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

        {/* RIGHT COLUMN — Alternatives */}
        {(hasAlternatives || analysisLoading) && (
          <div className="lg:col-span-2 space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Alternatives Considered
            </h3>

            {analysisLoading && (
              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-center gap-2">
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                    <span className="text-sm text-muted-foreground">Loading alternatives...</span>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Trip-Window Proposals */}
            {tripWindow && tripWindow.proposals.length > 0 && (
              <Card className="border-blue-200">
                <CardContent className="pt-5 space-y-3">
                  <div>
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-blue-700">
                      Shift Your Trip Dates
                    </h4>
                    <p className="text-[10px] text-blue-600 mt-0.5">
                      Same {tripWindow.original_trip_duration}-day trip, different dates
                    </p>
                  </div>
                  {tripWindow.proposals.map((proposal) => (
                    <TripWindowCard key={`${proposal.outbound_date}-${proposal.return_date}`} proposal={proposal} />
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Same-Day Alternatives Per Leg */}
            {analysis?.legs?.some((l) => l.alternatives.length > 0) && (
              <Card>
                <CardContent className="pt-5 space-y-3">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Same-Day Alternatives
                  </h4>
                  {analysis.legs.map((leg) => {
                    if (!leg.alternatives.length || !leg.selected) return null;
                    return (
                      <div key={leg.leg_id} className="space-y-1.5">
                        <p className="text-xs font-medium text-muted-foreground">
                          Leg {leg.sequence}: {leg.route}
                        </p>
                        {leg.alternatives.map((alt) => (
                          <div
                            key={alt.flight_option_id}
                            className="flex items-center justify-between rounded-md border border-border bg-muted/20 px-3 py-2"
                          >
                            <div>
                              <span className="text-sm font-medium">{alt.airline}</span>
                              <span className="text-xs text-muted-foreground ml-2">
                                {alt.stops === 0 ? "Nonstop" : `${alt.stops} stop${alt.stops > 1 ? "s" : ""}`}
                              </span>
                            </div>
                            <div className="text-right">
                              <span className="text-sm font-bold text-emerald-700">
                                {formatPrice(alt.price)}
                              </span>
                              {alt.savings > 0 && (
                                <span className="text-[10px] text-emerald-600 ml-1">
                                  ({formatPrice(alt.savings)} less)
                                </span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            )}

            {/* Different Month Options */}
            {tripWindow?.different_month && tripWindow.different_month.length > 0 && (
              <Card className="border-purple-200">
                <CardContent className="pt-5 space-y-3">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-purple-700">
                    Different Month Options
                  </h4>
                  <p className="text-[10px] text-purple-600">
                    Same trip, significantly different dates
                  </p>
                  {tripWindow.different_month.map((proposal) => (
                    <TripWindowCard key={`dm-${proposal.outbound_date}-${proposal.return_date}`} proposal={proposal} />
                  ))}
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
