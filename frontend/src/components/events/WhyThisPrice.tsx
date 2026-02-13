import type { DateEvent } from "@/types/event";
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
  date: string;
  events: DateEvent[];
  price: number;
  onClose: () => void;
}

export function WhyThisPrice({ date, events, price, onClose }: Props) {
  const formattedDate = new Date(date + "T12:00:00").toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  const hasEvents = events.length > 0;
  const totalImpact = hasEvents
    ? Math.max(...events.map((e) => e.price_increase_pct))
    : 0;

  const dayOfWeek = new Date(date + "T12:00:00").getDay();
  const isWeekend = dayOfWeek === 0 || dayOfWeek === 5 || dayOfWeek === 6;

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Why This Price?</h3>
        <button
          onClick={onClose}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Close
        </button>
      </div>

      <div>
        <p className="text-xs text-muted-foreground">{formattedDate}</p>
        <p className="text-lg font-bold mt-0.5">${Math.round(price)}</p>
      </div>

      <div className="space-y-3">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          Price Factors
        </h4>

        {/* Day of week factor */}
        <div className="flex items-center gap-3 text-xs">
          <span className="w-5 text-center">
            {isWeekend ? "\uD83D\uDCC8" : "\uD83D\uDCC9"}
          </span>
          <span className="flex-1">
            {isWeekend
              ? "Weekend / Friday travel tends to cost more"
              : "Midweek travel — typically lower fares"}
          </span>
          <span
            className={isWeekend ? "text-orange-600 font-medium" : "text-emerald-600 font-medium"}
          >
            {isWeekend ? "+10-20%" : "-5-15%"}
          </span>
        </div>

        {/* Event factors */}
        {hasEvents ? (
          events.map((evt, i) => {
            const icon = categoryIcons[evt.icon] || categoryIcons.calendar;
            return (
              <div key={i} className="flex items-start gap-3 text-xs">
                <span className="w-5 text-center mt-0.5">{icon}</span>
                <div className="flex-1">
                  <p className="font-medium">{evt.title}</p>
                  <div className="mt-1 max-w-[140px]">
                    <EventImpactBar level={evt.impact_level} />
                  </div>
                  {evt.attendance && (
                    <p className="text-muted-foreground mt-0.5">
                      ~{evt.attendance >= 1000
                        ? `${Math.round(evt.attendance / 1000)}K`
                        : evt.attendance}{" "}
                      visitors increase hotel & flight demand
                    </p>
                  )}
                </div>
                <span className="text-red-600 font-medium whitespace-nowrap">
                  +{Math.round(evt.price_increase_pct * 100)}%
                </span>
              </div>
            );
          })
        ) : (
          <div className="flex items-center gap-3 text-xs">
            <span className="w-5 text-center">
              {"\u2705"}
            </span>
            <span className="flex-1 text-emerald-600">
              No major events — prices at normal levels
            </span>
          </div>
        )}
      </div>

      {/* Estimated total impact */}
      {hasEvents && (
        <div className="border-t border-border pt-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Estimated event impact</span>
            <span className="font-semibold text-red-600">
              +{Math.round(totalImpact * 100)}% above normal
            </span>
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">
            Consider dates without major events to save on travel costs.
          </p>
        </div>
      )}
    </div>
  );
}
