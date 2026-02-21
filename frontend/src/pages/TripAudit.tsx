import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import apiClient from "@/api/client";
import { formatPrice } from "@/lib/currency";

interface TimelineEvent {
  timestamp: string;
  event: string;
  actor: string;
  details: Record<string, unknown>;
}

const eventConfig: Record<string, { color: string; label: string; icon: string }> = {
  trip_created:        { color: "bg-blue-500",   label: "Trip Created",       icon: "+" },
  search_executed:     { color: "bg-cyan-500",   label: "Search Executed",    icon: "?" },
  date_shift_selected: { color: "bg-purple-500", label: "Date Shift Selected",icon: "~" },
  flights_confirmed:   { color: "bg-blue-500",   label: "Flights Confirmed",  icon: "v" },
  hotel_selected:      { color: "bg-teal-500",   label: "Hotel Selected",     icon: "H" },
  trip_submitted:      { color: "bg-indigo-500", label: "Trip Submitted",     icon: ">" },
  approval_viewed:     { color: "bg-gray-400",   label: "Approval Viewed",    icon: "o" },
  trip_approved:       { color: "bg-green-500",  label: "Trip Approved",      icon: "v" },
  trip_rejected:       { color: "bg-red-500",    label: "Trip Rejected",      icon: "x" },
  changes_requested:   { color: "bg-orange-500", label: "Changes Requested",  icon: "!" },
  approval_escalated:  { color: "bg-purple-500", label: "Escalated",          icon: "^" },
  comment_added:       { color: "bg-gray-400",   label: "Comment",            icon: "#" },
};

function EventDetails({ event }: { event: TimelineEvent }) {
  const d = event.details;

  switch (event.event) {
    case "trip_created":
      return (
        <div className="text-xs text-muted-foreground space-y-0.5">
          <span className="capitalize">{String(d.method || "").replace("_", " ")}</span>
          {d.input && <p className="font-medium text-foreground">{String(d.input)}</p>}
        </div>
      );

    case "search_executed":
      return (
        <div className="text-xs text-muted-foreground space-y-0.5">
          {Array.isArray(d.legs) && (
            <p>{(d.legs as string[]).join(", ")}</p>
          )}
          <div className="flex gap-3">
            <span>{String(d.total_options)} options found</span>
            {d.cheapest != null && <span>cheapest: {formatPrice(d.cheapest as number)}</span>}
            {d.most_expensive != null && <span>most expensive: {formatPrice(d.most_expensive as number)}</span>}
          </div>
        </div>
      );

    case "date_shift_selected": {
      const origDates = d.original_dates as string[] | null;
      const newDates = d.new_dates as string[] | null;
      return (
        <div className="text-xs space-y-1">
          <p className="text-muted-foreground">Traveler shifted dates via trip-window alternatives</p>
          {origDates && newDates && (
            <div className="space-y-0.5">
              {origDates.map((od, i) => (
                <p key={i} className="text-muted-foreground">
                  {od.split(":")[0]}: <span className="line-through">{od.split(": ")[1]}</span>
                  {" → "}
                  <span className="font-medium text-foreground">{newDates[i]?.split(": ")[1]}</span>
                </p>
              ))}
            </div>
          )}
          <div className="flex gap-3 text-muted-foreground">
            {d.original_total != null && <span>Original: {formatPrice(d.original_total as number)}</span>}
            {d.new_total != null && <span>Shifted: {formatPrice(d.new_total as number)}</span>}
          </div>
          {(d.savings as number) > 0 && (
            <p className="text-emerald-600 font-medium">
              Saved {formatPrice(d.savings as number)} by shifting dates
            </p>
          )}
        </div>
      );
    }

    case "flights_confirmed": {
      const flights = d.flights as Array<Record<string, unknown>> | undefined;
      return (
        <div className="text-xs space-y-1">
          {flights?.map((f, i) => (
            <div key={i} className="flex items-center gap-2 text-muted-foreground">
              <span className="font-medium text-foreground">{String(f.leg)}</span>
              <span>{String(f.airline)}</span>
              <span>{String(f.date)}</span>
              <span>{formatPrice(f.price as number, f.currency as string)}</span>
              <span>{f.stops === 0 ? "Nonstop" : `${f.stops} stop${(f.stops as number) > 1 ? "s" : ""}`}</span>
            </div>
          ))}
          {d.total != null && (
            <p className="font-medium text-foreground pt-0.5">
              Total: {formatPrice(d.total as number, d.currency as string)}
            </p>
          )}
        </div>
      );
    }

    case "trip_submitted":
      return (
        <div className="text-xs text-muted-foreground space-y-0.5">
          {d.total != null && <span>Total: {formatPrice(d.total as number)}</span>}
          {d.sent_to && <p>Sent to <span className="font-medium text-foreground">{String(d.sent_to)}</span> for approval</p>}
        </div>
      );

    case "hotel_selected":
      return (
        <div className="text-xs text-muted-foreground space-y-0.5">
          <span>{String(d.leg)}</span>
          {d.hotel && <span className="font-medium text-foreground ml-2">{String(d.hotel)}</span>}
          {d.total_rate != null && <span className="ml-2">{formatPrice(d.total_rate as number)}</span>}
          {d.check_in && <span className="ml-2">{String(d.check_in)} → {String(d.check_out)}</span>}
        </div>
      );

    default: {
      // Generic fallback for approval events, comments, etc.
      const entries = Object.entries(d).filter(([, v]) => v != null);
      if (entries.length === 0) return null;
      return (
        <div className="text-xs text-muted-foreground">
          {entries.map(([k, v]) => (
            <span key={k} className="mr-3">
              {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
            </span>
          ))}
        </div>
      );
    }
  }
}

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

              {timeline.map((event, i) => {
                const cfg = eventConfig[event.event] || { color: "bg-gray-400", label: event.event, icon: "." };
                return (
                  <div key={i} className="flex gap-4 py-3 relative">
                    <div
                      className={`w-4 h-4 rounded-full shrink-0 mt-0.5 ${cfg.color}`}
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{cfg.label}</span>
                        <span className="text-xs text-muted-foreground">
                          by {event.actor}
                        </span>
                      </div>
                      <div className="mt-1">
                        <EventDetails event={event} />
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {new Date(event.timestamp).toLocaleString()}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
