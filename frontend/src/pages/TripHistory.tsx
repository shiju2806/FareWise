import { useEffect } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useTripStore } from "@/stores/tripStore";
import { useAuthStore } from "@/stores/authStore";
import { useApprovalStore } from "@/stores/approvalStore";
import { LegList } from "@/components/trip/LegList";

const statusBadge: Record<string, string> = {
  draft: "bg-gray-100 text-gray-700",
  searching: "bg-blue-100 text-blue-700",
  submitted: "bg-amber-100 text-amber-700",
  approved: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
  changes_requested: "bg-orange-100 text-orange-700",
};

export default function TripHistory() {
  const { trips, loading, fetchTrips, deleteTrip } = useTripStore();
  const user = useAuthStore((s) => s.user);
  const { counts, fetchApprovals } = useApprovalStore();

  useEffect(() => {
    fetchTrips();
    if (user?.role === "manager" || user?.role === "admin") {
      fetchApprovals();
    }
  }, [fetchTrips, fetchApprovals, user]);

  const draftCount = trips.filter((t) => t.status === "draft").length;
  const submittedCount = trips.filter((t) => t.status === "submitted").length;
  const approvedCount = trips.filter((t) => t.status === "approved").length;
  const isManager = user?.role === "manager" || user?.role === "admin";

  return (
    <div className="space-y-6">
      {/* Header with stats bar */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">My Trips</h2>
          <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
            <span>{trips.length} trips</span>
            <span className="text-border">|</span>
            <span>{draftCount} draft</span>
            <span className="text-border">|</span>
            <span className="text-amber-600">{submittedCount} submitted</span>
            <span className="text-border">|</span>
            <span className="text-green-600">{approvedCount} approved</span>
            {isManager && counts.pending > 0 && (
              <>
                <span className="text-border">|</span>
                <Link to="/approvals" className="text-primary font-medium hover:underline">
                  {counts.pending} pending approval{counts.pending > 1 ? "s" : ""}
                </Link>
              </>
            )}
          </div>
        </div>
        <Link to="/trips/new">
          <Button>New Trip</Button>
        </Link>
      </div>

      {loading && trips.length === 0 && (
        <div className="text-center py-12 text-muted-foreground text-sm">
          Loading trips...
        </div>
      )}

      {!loading && trips.length === 0 && (
        <div className="text-center py-12 space-y-3">
          <p className="text-muted-foreground">No trips yet.</p>
          <Link to="/trips/new">
            <Button variant="outline">Plan your first trip</Button>
          </Link>
        </div>
      )}

      <div className="space-y-4">
        {trips.map((trip) => (
          <div
            key={trip.id}
            className="rounded-lg border border-border p-5 space-y-3"
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold">
                    {trip.title || "Untitled Trip"}
                  </h3>
                  <span
                    className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      statusBadge[trip.status] || "bg-gray-100"
                    }`}
                  >
                    {trip.status}
                  </span>
                </div>
                <div className="flex gap-3 mt-1 text-xs text-muted-foreground">
                  <span>
                    Created {new Date(trip.created_at).toLocaleDateString()}
                  </span>
                  {trip.total_estimated_cost && (
                    <span>
                      Est. {trip.currency} {trip.total_estimated_cost.toFixed(0)}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex gap-2">
                {trip.status === "draft" && (
                  <>
                    <Link to={`/trips/${trip.id}/search`}>
                      <Button size="sm">Search Flights</Button>
                    </Link>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        if (confirm("Delete this trip?")) {
                          deleteTrip(trip.id);
                        }
                      }}
                    >
                      Delete
                    </Button>
                  </>
                )}
                {trip.status === "searching" && (
                  <>
                    <Link to={`/trips/${trip.id}/search`}>
                      <Button size="sm" variant="outline">
                        View Results
                      </Button>
                    </Link>
                    <Link to={`/trips/${trip.id}/review`}>
                      <Button size="sm">Review & Submit</Button>
                    </Link>
                  </>
                )}
                {trip.status === "submitted" && (
                  <Link to={`/trips/${trip.id}/audit`}>
                    <Button size="sm" variant="outline">
                      View Status
                    </Button>
                  </Link>
                )}
                {(trip.status === "approved" || trip.status === "rejected") && (
                  <Link to={`/trips/${trip.id}/audit`}>
                    <Button size="sm" variant="outline">
                      Audit Trail
                    </Button>
                  </Link>
                )}
                {trip.status === "changes_requested" && (
                  <>
                    <Link to={`/trips/${trip.id}/search`}>
                      <Button size="sm">Revise</Button>
                    </Link>
                    <Link to={`/trips/${trip.id}/review`}>
                      <Button size="sm" variant="outline">
                        Resubmit
                      </Button>
                    </Link>
                  </>
                )}
              </div>
            </div>

            {trip.legs.length > 0 && <LegList legs={trip.legs} />}
          </div>
        ))}
      </div>
    </div>
  );
}
