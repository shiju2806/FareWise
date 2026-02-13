import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { GroupTripSummary } from "@/types/collaboration";

interface Props {
  trip: GroupTripSummary;
  onView: (id: string) => void;
  onAccept?: (id: string) => void;
  onDecline?: (id: string) => void;
}

export function GroupTripCard({ trip, onView, onAccept, onDecline }: Props) {
  const isPending = trip.my_status === "invited";

  return (
    <Card className="hover:border-primary/30 transition-colors">
      <CardContent className="pt-4 pb-3">
        <div className="flex items-start justify-between">
          <div className="min-w-0 flex-1">
            <button
              type="button"
              onClick={() => onView(trip.id)}
              className="text-sm font-semibold hover:underline text-left"
            >
              {trip.name}
            </button>
            <p className="text-xs text-muted-foreground mt-0.5">
              {trip.destination_city} · {trip.start_date} — {trip.end_date}
            </p>
            <p className="text-xs text-muted-foreground">
              Organized by {trip.organizer} ·{" "}
              {trip.accepted_count}/{trip.member_count} confirmed
            </p>
          </div>
          <div className="flex items-center gap-2 ml-3">
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${
                trip.status === "planning"
                  ? "bg-blue-100 text-blue-700"
                  : trip.status === "confirmed"
                  ? "bg-green-100 text-green-700"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {trip.status}
            </span>
          </div>
        </div>

        {isPending && (
          <div className="flex gap-2 mt-3">
            <Button
              size="sm"
              variant="default"
              onClick={() => onAccept?.(trip.id)}
            >
              Accept
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onDecline?.(trip.id)}
            >
              Decline
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
