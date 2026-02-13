import type { BundleOption } from "@/types/bundle";
import { BundleSavingsTag } from "./BundleSavingsTag";

interface Props {
  bundle: BundleOption;
}

const strategyColors: Record<string, string> = {
  best_value: "border-emerald-300 bg-emerald-50",
  preferred: "border-blue-300 bg-blue-50",
  cheapest: "border-amber-300 bg-amber-50",
};

export function BundleCard({ bundle }: Props) {
  const color = strategyColors[bundle.strategy || ""] || "border-border";
  const depDate = new Date(bundle.departure_date + "T12:00:00");
  const formatted = depDate.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });

  return (
    <div className={`rounded-lg border-2 p-4 space-y-3 ${color}`}>
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-semibold">{bundle.label || "Option"}</h4>
          <p className="text-xs text-muted-foreground">Depart {formatted}</p>
        </div>
        <div className="text-right">
          <p className="text-lg font-bold">${Math.round(bundle.combined_total)}</p>
          <p className="text-[10px] text-muted-foreground">total</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-background/60 rounded p-2">
          <p className="text-muted-foreground">Flight</p>
          <p className="font-semibold">${Math.round(bundle.flight_cost)}</p>
        </div>
        <div className="bg-background/60 rounded p-2">
          <p className="text-muted-foreground">Hotel</p>
          <p className="font-semibold">
            ${Math.round(bundle.hotel_total)}
            <span className="font-normal text-muted-foreground ml-1">
              (${Math.round(bundle.hotel_nightly)}/night)
            </span>
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between">
        {bundle.savings_vs_preferred && bundle.savings_vs_preferred > 0 ? (
          <BundleSavingsTag savings={bundle.savings_vs_preferred} />
        ) : (
          <span />
        )}
        {bundle.events.length > 0 && (
          <span className="text-[10px] text-amber-600">
            {bundle.events.length} event(s) on this date
          </span>
        )}
      </div>
    </div>
  );
}
