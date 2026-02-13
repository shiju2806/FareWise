import type { DateEvent } from "@/types/event";

const impactColors: Record<string, string> = {
  low: "text-gray-600",
  medium: "text-amber-600",
  high: "text-orange-600",
  very_high: "text-red-600",
};

const impactLabels: Record<string, string> = {
  low: "Low impact",
  medium: "Medium impact",
  high: "High impact",
  very_high: "Very high impact",
};

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
  events: DateEvent[];
  date: string;
}

export function EventTooltip({ events, date }: Props) {
  if (events.length === 0) return null;

  const formattedDate = new Date(date + "T12:00:00").toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });

  return (
    <div className="bg-popover border border-border rounded-lg shadow-lg p-3 min-w-[240px] max-w-[320px] z-50">
      <p className="text-xs font-semibold text-foreground mb-2">
        Events on {formattedDate}
      </p>
      <div className="space-y-2">
        {events.map((evt, i) => {
          const icon = categoryIcons[evt.icon] || categoryIcons.calendar;
          return (
            <div key={i} className="flex items-start gap-2">
              <span className="text-sm mt-0.5">{icon}</span>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-foreground truncate">
                  {evt.title}
                </p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span
                    className={`text-[10px] font-medium ${impactColors[evt.impact_level]}`}
                  >
                    {impactLabels[evt.impact_level]}
                  </span>
                  {evt.attendance && (
                    <span className="text-[10px] text-muted-foreground">
                      {evt.attendance >= 1000
                        ? `${Math.round(evt.attendance / 1000)}K`
                        : evt.attendance}{" "}
                      expected
                    </span>
                  )}
                </div>
                <p className="text-[10px] text-muted-foreground mt-0.5">
                  Est. price impact: +{Math.round(evt.price_increase_pct * 100)}%
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
