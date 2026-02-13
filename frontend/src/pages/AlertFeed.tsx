import { useEffect } from "react";
import { usePriceWatchStore } from "@/stores/priceWatchStore";
import { AlertFeedItem } from "@/components/pricewatch/AlertFeedItem";

export default function AlertFeed() {
  const { alerts, unreadAlertCount, loadingAlerts, fetchAlerts } =
    usePriceWatchStore();

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  const priceDrops = alerts.filter((a) => a.type === "price_drop");
  const reminders = alerts.filter((a) => a.type === "booking_reminder");
  const eventWarnings = alerts.filter((a) => a.type === "event_warning");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Alerts</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Price drops, booking reminders, and event warnings.
          {unreadAlertCount > 0 && (
            <span className="ml-2 text-primary font-medium">
              {unreadAlertCount} unread
            </span>
          )}
        </p>
      </div>

      {loadingAlerts ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-20 bg-muted animate-pulse rounded-lg"
            />
          ))}
        </div>
      ) : alerts.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-muted-foreground">
            No alerts yet. Create a price watch to start receiving alerts.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {priceDrops.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold mb-2">Price Drops</h3>
              <div className="space-y-2">
                {priceDrops.map((a) => (
                  <AlertFeedItem key={a.id} alert={a} />
                ))}
              </div>
            </section>
          )}

          {reminders.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold mb-2">Booking Reminders</h3>
              <div className="space-y-2">
                {reminders.map((a) => (
                  <AlertFeedItem key={a.id} alert={a} />
                ))}
              </div>
            </section>
          )}

          {eventWarnings.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold mb-2">Event Warnings</h3>
              <div className="space-y-2">
                {eventWarnings.map((a) => (
                  <AlertFeedItem key={a.id} alert={a} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
