import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApprovalStore } from "@/stores/approvalStore";
import { formatPrice } from "@/lib/currency";

const statusColors: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800",
  approved: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
  changes_requested: "bg-orange-100 text-orange-800",
  escalated: "bg-purple-100 text-purple-800",
};

const policyStatusIcons: Record<string, string> = {
  compliant: "text-green-600",
  warning: "text-amber-600",
  violation: "text-red-600",
};

export default function ApprovalDashboard() {
  const { approvals, counts, loading, fetchApprovals } = useApprovalStore();
  const [filter, setFilter] = useState<string | undefined>(undefined);

  useEffect(() => {
    fetchApprovals(filter);
  }, [fetchApprovals, filter]);

  const tabs = [
    { label: "All", value: undefined, count: undefined },
    { label: "Pending", value: "pending", count: counts.pending },
    { label: "Approved", value: "approved", count: counts.approved },
    { label: "Rejected", value: "rejected", count: counts.rejected },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Approvals</h2>
        <p className="text-muted-foreground mt-1">
          Review and manage trip approval requests.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        {tabs.map((tab) => (
          <Button
            key={tab.label}
            variant={filter === tab.value ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter(tab.value)}
          >
            {tab.label}
            {tab.count !== undefined && tab.count > 0 && (
              <span className="ml-1.5 bg-primary-foreground/20 rounded-full px-1.5 text-xs">
                {tab.count}
              </span>
            )}
          </Button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-28 bg-muted animate-pulse rounded-lg" />
          ))}
        </div>
      ) : approvals.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-lg">No approval requests</p>
          <p className="text-sm mt-1">
            {filter
              ? `No ${filter} approvals found.`
              : "You have no approval requests at this time."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {approvals.map((approval) => (
            <Link
              key={approval.id}
              to={`/approvals/${approval.id}`}
            >
              <Card className="hover:border-primary/30 transition-colors cursor-pointer">
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold">
                          {approval.trip.title || "Untitled Trip"}
                        </h3>
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                            statusColors[approval.status] || "bg-gray-100"
                          }`}
                        >
                          {approval.status}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {approval.trip.traveler.name}
                        {approval.trip.traveler.department &&
                          ` · ${approval.trip.traveler.department}`}
                        {approval.trip.travel_dates &&
                          ` · ${approval.trip.travel_dates}`}
                      </p>
                      {approval.savings_report?.narrative && (
                        <p className="text-sm text-muted-foreground line-clamp-2">
                          {approval.savings_report.narrative}
                        </p>
                      )}
                    </div>
                    <div className="text-right space-y-1">
                      {approval.trip.total_estimated_cost && (
                        <p className="text-lg font-bold">
                          {formatPrice(approval.trip.total_estimated_cost)}
                        </p>
                      )}
                      {approval.savings_report && (
                        <p
                          className={`text-xs font-medium ${
                            policyStatusIcons[
                              approval.savings_report.policy_status || ""
                            ] || ""
                          }`}
                        >
                          {approval.savings_report.policy_status === "compliant"
                            ? "Policy Compliant"
                            : approval.savings_report.policy_status === "warning"
                            ? `${approval.warnings_count} Warning(s)`
                            : "Violations"}
                        </p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        {new Date(approval.created_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
