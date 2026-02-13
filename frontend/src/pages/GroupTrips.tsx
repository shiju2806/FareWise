import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCollaborationStore } from "@/stores/collaborationStore";
import { GroupTripCard } from "@/components/collaboration/GroupTripCard";
import { GroupTripCreate } from "@/components/collaboration/GroupTripCreate";
import { Button } from "@/components/ui/button";

export default function GroupTrips() {
  const navigate = useNavigate();
  const {
    groupTrips,
    loading,
    fetchGroupTrips,
    createGroupTrip,
    acceptInvite,
    declineInvite,
  } = useCollaborationStore();
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    fetchGroupTrips();
  }, [fetchGroupTrips]);

  async function handleCreate(data: Parameters<typeof createGroupTrip>[0]) {
    const id = await createGroupTrip(data);
    if (id) {
      setShowCreate(false);
    }
  }

  if (loading && groupTrips.length === 0) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="h-24 bg-muted animate-pulse rounded-lg" />
        <div className="h-24 bg-muted animate-pulse rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Group Trips</h2>
          <p className="text-muted-foreground mt-1">
            Coordinate travel with colleagues.
          </p>
        </div>
        <Button
          variant={showCreate ? "outline" : "default"}
          size="sm"
          onClick={() => setShowCreate(!showCreate)}
        >
          {showCreate ? "Cancel" : "New Group Trip"}
        </Button>
      </div>

      {showCreate && (
        <GroupTripCreate onSubmit={handleCreate} loading={loading} />
      )}

      {groupTrips.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-lg font-medium">No group trips yet</p>
          <p className="text-sm text-muted-foreground mt-1">
            Create one to start coordinating with your team!
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {groupTrips.map((trip) => (
            <GroupTripCard
              key={trip.id}
              trip={trip}
              onView={(id) => navigate(`/group-trips/${id}`)}
              onAccept={acceptInvite}
              onDecline={declineInvite}
            />
          ))}
        </div>
      )}
    </div>
  );
}
