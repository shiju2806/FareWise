import { useEffect } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTripStore } from "@/stores/tripStore";
import { useAuthStore } from "@/stores/authStore";
import { useApprovalStore } from "@/stores/approvalStore";

export default function Dashboard() {
  const { trips, fetchTrips } = useTripStore();
  const user = useAuthStore((s) => s.user);
  const { counts, fetchApprovals } = useApprovalStore();

  useEffect(() => {
    fetchTrips();
    if (user?.role === "manager" || user?.role === "admin") {
      fetchApprovals();
    }
  }, [fetchTrips, fetchApprovals, user]);

  const draftCount = trips.filter((t) => t.status === "draft").length;
  const searchingCount = trips.filter((t) => t.status === "searching").length;
  const submittedCount = trips.filter((t) => t.status === "submitted").length;
  const approvedCount = trips.filter((t) => t.status === "approved").length;
  const totalTrips = trips.length;
  const isManager = user?.role === "manager" || user?.role === "admin";

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Dashboard</h2>
        <p className="text-muted-foreground mt-1">
          Welcome to FareWise. Plan trips, search flights, and optimize costs.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Trips
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{totalTrips}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Drafts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{draftCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Submitted
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-amber-600">
              {submittedCount}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Approved
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-green-600">
              {approvedCount}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Manager approval card */}
      {isManager && counts.pending > 0 && (
        <Card className="border-amber-200 bg-amber-50/50">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">
                  {counts.pending} Pending Approval
                  {counts.pending > 1 ? "s" : ""}
                </p>
                <p className="text-sm text-muted-foreground">
                  Trips waiting for your review
                </p>
              </div>
              <Link to="/approvals">
                <Button>Review Now</Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex gap-3">
        <Link to="/trips/new">
          <Button>New Trip</Button>
        </Link>
        <Link to="/trips">
          <Button variant="outline">View All Trips</Button>
        </Link>
        {isManager && (
          <Link to="/approvals">
            <Button variant="outline">Approvals</Button>
          </Link>
        )}
      </div>
    </div>
  );
}
