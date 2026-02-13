import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import apiClient from "@/api/client";

interface TimelineEvent {
  timestamp: string;
  event: string;
  actor: string;
  details: Record<string, unknown>;
}

const eventColors: Record<string, string> = {
  trip_created: "bg-blue-500",
  search_executed: "bg-gray-400",
  slider_adjusted: "bg-gray-400",
  flight_selected: "bg-blue-500",
  trip_submitted: "bg-indigo-500",
  approval_created: "bg-amber-500",
  approval_viewed: "bg-gray-400",
  trip_approved: "bg-green-500",
  trip_rejected: "bg-red-500",
  changes_requested: "bg-orange-500",
  approval_escalated: "bg-purple-500",
  comment_added: "bg-gray-400",
};

const eventLabels: Record<string, string> = {
  trip_created: "Trip Created",
  search_executed: "Search Executed",
  slider_adjusted: "Slider Adjusted",
  flight_selected: "Flight Selected",
  trip_submitted: "Trip Submitted",
  approval_created: "Approval Created",
  approval_viewed: "Approval Viewed",
  trip_approved: "Trip Approved",
  trip_rejected: "Trip Rejected",
  changes_requested: "Changes Requested",
  approval_escalated: "Escalated",
  comment_added: "Comment",
};

export default function TripAudit() {
  const { tripId } = useParams<{ tripId: string }>();
  const navigate = useNavigate();
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tripId) return;
    apiClient
      .get(`/audit/trip/${tripId}`)
      .then((res) => setTimeline(res.data.timeline))
      .catch(() => setTimeline([]))
      .finally(() => setLoading(false));
  }, [tripId]);

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-16 bg-muted animate-pulse rounded" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate(-1)}
          className="mb-2"
        >
          &larr; Back
        </Button>
        <h2 className="text-2xl font-bold tracking-tight">Audit Trail</h2>
        <p className="text-muted-foreground mt-1">
          Complete activity timeline for this trip.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          {timeline.length === 0 ? (
            <p className="text-muted-foreground text-center py-4">
              No events recorded.
            </p>
          ) : (
            <div className="relative space-y-0">
              {/* Vertical line */}
              <div className="absolute left-[7px] top-2 bottom-2 w-0.5 bg-muted" />

              {timeline.map((event, i) => (
                <div key={i} className="flex gap-4 py-3 relative">
                  <div
                    className={`w-4 h-4 rounded-full shrink-0 mt-0.5 ${
                      eventColors[event.event] || "bg-gray-400"
                    }`}
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">
                        {eventLabels[event.event] || event.event}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        by {event.actor}
                      </span>
                    </div>
                    {event.details && Object.keys(event.details).length > 0 && (
                      <div className="mt-1 text-xs text-muted-foreground">
                        {Object.entries(event.details)
                          .filter(([, v]) => v != null)
                          .map(([k, v]) => (
                            <span key={k} className="mr-3">
                              {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
                            </span>
                          ))}
                      </div>
                    )}
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {new Date(event.timestamp).toLocaleString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
