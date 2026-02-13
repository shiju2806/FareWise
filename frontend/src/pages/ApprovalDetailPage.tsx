import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import apiClient from "@/api/client";
import { useAuthStore } from "@/stores/authStore";

interface ApprovalDetail {
  id: string;
  status: string;
  comments: string | null;
  decided_at: string | null;
  created_at: string;
  trip: {
    id: string;
    title: string;
    status: string;
    legs: Array<{
      id: string;
      sequence: number;
      origin_airport: string;
      origin_city: string;
      destination_airport: string;
      destination_city: string;
      preferred_date: string;
      cabin_class: string;
      passengers: number;
    }>;
    total_estimated_cost: number | null;
  };
  traveler: { id: string; name: string; department: string | null };
  approver: { id: string; name: string };
  savings_report: {
    id: string;
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
  } | null;
  history: Array<{
    id: string;
    action: string;
    actor: string;
    details: Record<string, unknown> | null;
    created_at: string;
  }>;
}

const statusColors: Record<string, string> = {
  pass: "text-green-600",
  warn: "text-amber-600",
  block: "text-red-600",
  info: "text-blue-600",
};

const statusIcons: Record<string, string> = {
  pass: "✓",
  warn: "⚠",
  block: "✕",
  info: "ℹ",
};

export default function ApprovalDetailPage() {
  const { approvalId } = useParams<{ approvalId: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [detail, setDetail] = useState<ApprovalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [comment, setComment] = useState("");
  const [acting, setActing] = useState(false);

  useEffect(() => {
    if (!approvalId) return;
    setLoading(true);
    apiClient
      .get(`/approvals/${approvalId}`)
      .then((res) => setDetail(res.data))
      .catch(() => navigate("/approvals"))
      .finally(() => setLoading(false));
  }, [approvalId, navigate]);

  const handleDecide = async (action: string) => {
    if (!detail) return;
    setActing(true);
    try {
      await apiClient.post(`/approvals/${detail.id}/decide`, {
        action,
        comments: comment || undefined,
      });
      // Refresh
      const res = await apiClient.get(`/approvals/${detail.id}`);
      setDetail(res.data);
      setComment("");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Action failed";
      alert(message);
    } finally {
      setActing(false);
    }
  };

  const handleComment = async () => {
    if (!detail || !comment.trim()) return;
    setActing(true);
    try {
      await apiClient.post(`/approvals/${detail.id}/comment`, {
        comment: comment.trim(),
      });
      const res = await apiClient.get(`/approvals/${detail.id}`);
      setDetail(res.data);
      setComment("");
    } catch {
      alert("Failed to add comment");
    } finally {
      setActing(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="h-64 bg-muted animate-pulse rounded-lg" />
        <div className="h-48 bg-muted animate-pulse rounded-lg" />
      </div>
    );
  }

  if (!detail) return null;

  const sr = detail.savings_report;
  const isApprover = user?.id === detail.approver.id;
  const isPending = detail.status === "pending";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(-1)}
            className="mb-2"
          >
            &larr; Back
          </Button>
          <h2 className="text-2xl font-bold tracking-tight">
            {detail.trip.title || "Untitled Trip"}
          </h2>
          <p className="text-muted-foreground">
            {detail.traveler.name}
            {detail.traveler.department &&
              ` · ${detail.traveler.department}`}
          </p>
        </div>
        <div className="text-right">
          <span
            className={`px-3 py-1 rounded-full text-sm font-medium ${
              detail.status === "approved"
                ? "bg-green-100 text-green-800"
                : detail.status === "rejected"
                ? "bg-red-100 text-red-800"
                : detail.status === "pending"
                ? "bg-amber-100 text-amber-800"
                : "bg-gray-100 text-gray-800"
            }`}
          >
            {detail.status}
          </span>
        </div>
      </div>

      {/* Savings Card */}
      {sr && (
        <Card>
          <CardContent className="pt-6 space-y-4">
            {/* Cost Summary */}
            <div className="flex items-baseline justify-between">
              <span className="text-3xl font-bold">
                ${sr.selected_total.toFixed(0)} CAD
              </span>
              <span
                className={`text-sm font-medium ${
                  sr.policy_status === "compliant"
                    ? "text-green-600"
                    : sr.policy_status === "warning"
                    ? "text-amber-600"
                    : "text-red-600"
                }`}
              >
                {sr.policy_status === "compliant"
                  ? "Policy Compliant"
                  : sr.policy_status === "warning"
                  ? "Policy Warnings"
                  : "Policy Violations"}
              </span>
            </div>

            {/* Cost Comparison Bar */}
            <div className="relative h-3 bg-muted rounded-full overflow-hidden">
              <div
                className="absolute h-full bg-green-400 rounded-l-full"
                style={{
                  width: `${
                    ((sr.cheapest_total) / sr.most_expensive_total) * 100
                  }%`,
                }}
              />
              <div
                className="absolute h-full w-1 bg-primary"
                style={{
                  left: `${
                    (sr.selected_total / sr.most_expensive_total) * 100
                  }%`,
                }}
              />
            </div>
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Cheapest: ${sr.cheapest_total.toFixed(0)}</span>
              <span>Selected: ${sr.selected_total.toFixed(0)}</span>
              <span>Most Expensive: ${sr.most_expensive_total.toFixed(0)}</span>
            </div>

            {/* Narrative */}
            <div className="bg-muted/50 rounded-lg p-4">
              <p className="text-sm leading-relaxed">{sr.narrative}</p>
            </div>

            {/* Savings Stats */}
            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-3 bg-green-50 rounded-lg">
                <p className="text-2xl font-bold text-green-700">
                  ${sr.savings_vs_expensive.toFixed(0)}
                </p>
                <p className="text-xs text-green-600">
                  Saved vs. most expensive
                </p>
              </div>
              <div className="text-center p-3 bg-amber-50 rounded-lg">
                <p className="text-2xl font-bold text-amber-700">
                  ${sr.premium_vs_cheapest.toFixed(0)}
                </p>
                <p className="text-xs text-amber-600">
                  Premium over cheapest
                </p>
              </div>
            </div>

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
          </CardContent>
        </Card>
      )}

      {/* Trip Legs */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Itinerary</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {detail.trip.legs.map((leg) => (
              <div
                key={leg.id}
                className="flex items-center justify-between py-2 border-b last:border-0"
              >
                <div>
                  <span className="font-medium">
                    {leg.origin_airport} → {leg.destination_airport}
                  </span>
                  <span className="text-sm text-muted-foreground ml-2">
                    {leg.origin_city} → {leg.destination_city}
                  </span>
                </div>
                <div className="text-sm text-muted-foreground">
                  {leg.preferred_date} · {leg.cabin_class} ·{" "}
                  {leg.passengers} pax
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      {isApprover && isPending && (
        <Card>
          <CardContent className="pt-6 space-y-3">
            <textarea
              className="w-full border rounded-md px-3 py-2 text-sm bg-background"
              placeholder="Add a comment (optional)..."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={2}
            />
            <div className="flex gap-2">
              <Button
                onClick={() => handleDecide("approve")}
                disabled={acting}
                className="bg-green-600 hover:bg-green-700"
              >
                Approve
              </Button>
              <Button
                variant="outline"
                onClick={handleComment}
                disabled={acting || !comment.trim()}
              >
                Comment
              </Button>
              <Button
                variant="outline"
                onClick={() => handleDecide("changes_requested")}
                disabled={acting}
              >
                Request Changes
              </Button>
              <Button
                variant="outline"
                onClick={() => handleDecide("reject")}
                disabled={acting}
                className="text-red-600 border-red-300 hover:bg-red-50"
              >
                Reject
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Audit Timeline */}
      {detail.history.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Activity</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {detail.history.map((h) => (
                <div key={h.id} className="flex gap-3 text-sm">
                  <div className="w-2 h-2 mt-1.5 rounded-full bg-muted-foreground shrink-0" />
                  <div>
                    <p>
                      <span className="font-medium">{h.actor}</span>{" "}
                      <span className="text-muted-foreground">
                        {h.action}
                      </span>
                    </p>
                    {h.details &&
                      (h.details as Record<string, string>).comments && (
                        <p className="text-muted-foreground mt-0.5">
                          &ldquo;
                          {(h.details as Record<string, string>).comments}
                          &rdquo;
                        </p>
                      )}
                    {h.details &&
                      (h.details as Record<string, string>).comment && (
                        <p className="text-muted-foreground mt-0.5">
                          &ldquo;
                          {(h.details as Record<string, string>).comment}
                          &rdquo;
                        </p>
                      )}
                    <p className="text-xs text-muted-foreground">
                      {new Date(h.created_at).toLocaleString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
