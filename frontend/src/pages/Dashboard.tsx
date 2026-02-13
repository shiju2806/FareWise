import { useEffect } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTripStore } from "@/stores/tripStore";

export default function Dashboard() {
  const { trips, fetchTrips } = useTripStore();

  useEffect(() => {
    fetchTrips();
  }, [fetchTrips]);

  const draftCount = trips.filter((t) => t.status === "draft").length;
  const searchingCount = trips.filter((t) => t.status === "searching").length;
  const totalTrips = trips.length;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Dashboard</h2>
        <p className="text-muted-foreground mt-1">
          Welcome to FareWise. Plan trips, search flights, and find the best deals.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
              Searching
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{searchingCount}</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-3">
        <Link to="/trips/new">
          <Button>New Trip</Button>
        </Link>
        <Link to="/trips">
          <Button variant="outline">View All Trips</Button>
        </Link>
      </div>
    </div>
  );
}
