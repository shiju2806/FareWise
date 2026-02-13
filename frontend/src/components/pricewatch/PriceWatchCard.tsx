import { useState } from "react";
import { Button } from "@/components/ui/button";
import { PriceSparkline } from "./PriceSparkline";
import { usePriceWatchStore } from "@/stores/priceWatchStore";
import type { PriceWatch } from "@/types/priceWatch";

interface Props {
  watch: PriceWatch;
}

export function PriceWatchCard({ watch }: Props) {
  const deleteWatch = usePriceWatchStore((s) => s.deleteWatch);
  const [deleting, setDeleting] = useState(false);

  const trendIcon =
    watch.trend === "down" ? "\u2193" : watch.trend === "up" ? "\u2191" : "\u2192";
  const trendColor =
    watch.trend === "down"
      ? "text-green-600"
      : watch.trend === "up"
        ? "text-red-500"
        : "text-muted-foreground";

  const targetMet =
    watch.target_price &&
    watch.current_best_price &&
    watch.current_best_price <= watch.target_price;

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      {/* Header row */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">
              {watch.origin} &rarr; {watch.destination}
            </span>
            {targetMet && (
              <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded-full font-medium">
                Target met!
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {new Date(watch.target_date).toLocaleDateString("en-US", {
              weekday: "short",
              month: "short",
              day: "numeric",
            })}
            {watch.flexibility_days > 0 &&
              ` (\u00b1${watch.flexibility_days} days)`}
            {" \u00b7 "}
            {watch.cabin_class}
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          disabled={deleting}
          onClick={async () => {
            setDeleting(true);
            await deleteWatch(watch.id);
          }}
          className="text-muted-foreground hover:text-destructive"
        >
          {deleting ? "..." : "\u00d7"}
        </Button>
      </div>

      {/* Price row */}
      <div className="flex items-center gap-4">
        <div>
          <p className="text-xs text-muted-foreground">Current</p>
          <p className={`text-lg font-bold ${trendColor}`}>
            {watch.current_best_price
              ? `$${Math.round(watch.current_best_price)}`
              : "\u2014"}
            <span className="text-sm ml-1">{trendIcon}</span>
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Target</p>
          <p className="text-lg font-semibold text-muted-foreground">
            {watch.target_price ? `$${Math.round(watch.target_price)}` : "\u2014"}
          </p>
        </div>
        <div className="flex-1 flex justify-end">
          <PriceSparkline
            history={watch.price_history}
            trend={watch.trend}
          />
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {watch.alert_count > 0
            ? `${watch.alert_count} alert${watch.alert_count > 1 ? "s" : ""} sent`
            : "No alerts yet"}
        </span>
        <span>
          {watch.last_checked_at
            ? `Checked ${new Date(watch.last_checked_at).toLocaleString()}`
            : "Not yet checked"}
        </span>
      </div>
    </div>
  );
}
