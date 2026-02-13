import type { Alert } from "@/types/priceWatch";

interface Props {
  alert: Alert;
}

const typeConfig: Record<
  string,
  { icon: string; color: string; bgColor: string }
> = {
  price_drop: {
    icon: "\u2193",
    color: "text-green-700",
    bgColor: "bg-green-50 border-green-200",
  },
  booking_reminder: {
    icon: "\ud83c\udfe8",
    color: "text-amber-700",
    bgColor: "bg-amber-50 border-amber-200",
  },
  event_warning: {
    icon: "\u26a0",
    color: "text-orange-700",
    bgColor: "bg-orange-50 border-orange-200",
  },
};

export function AlertFeedItem({ alert }: Props) {
  const config = typeConfig[alert.type] || {
    icon: "\u2022",
    color: "text-foreground",
    bgColor: "bg-card",
  };

  return (
    <div
      className={`rounded-lg border p-3 ${config.bgColor} ${!alert.is_read ? "ring-1 ring-primary/20" : ""}`}
    >
      <div className="flex items-start gap-3">
        <span className="text-lg mt-0.5">{config.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`text-sm font-semibold ${config.color}`}>
              {alert.title}
            </span>
            {!alert.is_read && (
              <span className="w-2 h-2 rounded-full bg-primary flex-shrink-0" />
            )}
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">{alert.body}</p>
          <p className="text-xs text-muted-foreground mt-1.5">
            {alert.created_at
              ? new Date(alert.created_at).toLocaleString("en-US", {
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })
              : ""}
          </p>
        </div>
      </div>
    </div>
  );
}
