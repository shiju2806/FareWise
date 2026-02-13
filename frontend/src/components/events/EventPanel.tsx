import type { EventData } from "@/types/event";
import { EventImpactBar } from "./EventImpactBar";

const categoryIcons: Record<string, string> = {
  briefcase: "\uD83D\uDCBC",
  trophy: "\uD83C\uDFC6",
  music: "\uD83C\uDFB5",
  theater: "\uD83C\uDFAD",
  users: "\uD83D\uDC65",
  flag: "\uD83C\uDFF3\uFE0F",
  calendar: "\uD83D\uDCC5",
};

interface Props {
  events: EventData[];
  destination: string;
  onClose: () => void;
}

export function EventPanel({ events, destination, onClose }: Props) {
  if (events.length === 0) {
    return (
      <div className="rounded-lg border border-border p-4 bg-card">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">Events in {destination}</h3>
          <button
            onClick={onClose}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Close
          </button>
        </div>
        <p className="text-sm text-muted-foreground">
          No significant events found for these dates.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border p-4 bg-card">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold">
          Events in {destination}{" "}
          <span className="text-muted-foreground font-normal">
            ({events.length})
          </span>
        </h3>
        <button
          onClick={onClose}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Close
        </button>
      </div>

      <div className="space-y-3">
        {events.map((evt) => {
          const icon = categoryIcons[evt.icon] || categoryIcons.calendar;
          const dateRange =
            evt.start_date === evt.end_date
              ? new Date(evt.start_date + "T12:00:00").toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })
              : `${new Date(evt.start_date + "T12:00:00").toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })} - ${new Date(evt.end_date + "T12:00:00").toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })}`;

          return (
            <div
              key={evt.external_id}
              className="flex items-start gap-3 p-2 rounded-md hover:bg-accent/50"
            >
              <span className="text-lg mt-0.5">{icon}</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{evt.title}</p>
                <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
                  <span>{dateRange}</span>
                  {evt.venue_name && <span>{evt.venue_name}</span>}
                </div>
                <div className="mt-1.5 flex items-center gap-4">
                  <div className="flex-1 max-w-[120px]">
                    <EventImpactBar level={evt.impact_level} />
                  </div>
                  {evt.attendance && (
                    <span className="text-[10px] text-muted-foreground">
                      {evt.attendance >= 1000
                        ? `${Math.round(evt.attendance / 1000)}K`
                        : evt.attendance}{" "}
                      attendees
                    </span>
                  )}
                  <span className="text-[10px] text-muted-foreground">
                    +{Math.round(evt.price_increase_pct * 100)}% est. impact
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
