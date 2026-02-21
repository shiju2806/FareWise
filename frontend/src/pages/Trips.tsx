import { useState, useEffect } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { TripCalendar } from "@/components/trips/TripCalendar";
import { NewTripSlideOver } from "@/components/trips/NewTripSlideOver";
import { CompanySavingsGoal } from "@/components/gamification/CompanySavingsGoal";
import { useAuthStore } from "@/stores/authStore";
import { useApprovalStore } from "@/stores/approvalStore";
import { useAnalyticsStore } from "@/stores/analyticsStore";
import TripHistory from "./TripHistory";

type ViewMode = "calendar" | "list";

export default function Trips() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const user = useAuthStore((s) => s.user);
  const { counts, fetchApprovals } = useApprovalStore();
  const { savingsGoal, fetchSavingsGoal } = useAnalyticsStore();
  const [view, setView] = useState<ViewMode>(
    () => (localStorage.getItem("trips-view") as ViewMode) || "calendar"
  );
  const [showNewTrip, setShowNewTrip] = useState(false);
  const isManager = user?.role === "manager" || user?.role === "admin";

  // Auto-open slide-over if ?new=1 query param
  useEffect(() => {
    if (searchParams.get("new") === "1") {
      setShowNewTrip(true);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    fetchSavingsGoal();
    if (isManager) fetchApprovals();
  }, [fetchSavingsGoal, fetchApprovals, isManager]);

  function setViewMode(mode: ViewMode) {
    setView(mode);
    localStorage.setItem("trips-view", mode);
  }

  function handleTripCreated(tripId: string) {
    setShowNewTrip(false);
    navigate(`/trips/${tripId}/search`);
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold tracking-tight">Trips</h2>
        <div className="flex items-center gap-3">
          {/* View toggle */}
          <div className="flex rounded-md border border-border overflow-hidden">
            <button
              type="button"
              onClick={() => setViewMode("calendar")}
              className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
                view === "calendar"
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:bg-accent"
              }`}
              aria-label="Calendar view"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                />
              </svg>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("list")}
              className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
                view === "list"
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:bg-accent"
              }`}
              aria-label="List view"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              </svg>
            </button>
          </div>

          <Button size="sm" onClick={() => setShowNewTrip(true)}>
            + New Trip
          </Button>
        </div>
      </div>

      {/* Manager approval banner */}
      {isManager && counts.pending > 0 && (
        <Card className="border-amber-200 bg-amber-50/50">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">
                  {counts.pending} Pending Approval{counts.pending > 1 ? "s" : ""}
                </p>
                <p className="text-sm text-muted-foreground">
                  Trips waiting for your review
                </p>
              </div>
              <Link to="/approvals">
                <Button size="sm">Review Now</Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Company savings goal */}
      {savingsGoal && <CompanySavingsGoal goal={savingsGoal} />}

      {/* View content */}
      {view === "calendar" ? <TripCalendar /> : <TripHistory />}

      {/* Slide-over */}
      <NewTripSlideOver
        open={showNewTrip}
        onClose={() => setShowNewTrip(false)}
        onTripCreated={handleTripCreated}
      />
    </div>
  );
}
