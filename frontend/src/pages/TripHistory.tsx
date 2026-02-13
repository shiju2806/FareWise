import { useEffect } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useTripStore } from "@/stores/tripStore";
import { LegList } from "@/components/trip/LegList";

export default function TripHistory() {
  const { trips, loading, fetchTrips, deleteTrip } = useTripStore();

  useEffect(() => {
    fetchTrips();
  }, [fetchTrips]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">My Trips</h2>
          <p className="text-muted-foreground mt-1">
            View and manage your travel itineraries.
          </p>
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
                <h3 className="font-semibold">
                  {trip.title || "Untitled Trip"}
                </h3>
                <div className="flex gap-3 mt-1 text-xs text-muted-foreground">
                  <span className="capitalize">{trip.status}</span>
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
                  <Link to={`/trips/${trip.id}/search`}>
                    <Button size="sm" variant="outline">
                      View Results
                    </Button>
                  </Link>
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
