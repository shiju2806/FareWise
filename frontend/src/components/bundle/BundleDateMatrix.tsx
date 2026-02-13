import type { BundleOption } from "@/types/bundle";

interface Props {
  matrix: BundleOption[];
}

export function BundleDateMatrix({ matrix }: Props) {
  if (matrix.length === 0) return null;

  const costs = matrix.map((m) => m.combined_total);
  const minCost = Math.min(...costs);
  const maxCost = Math.max(...costs);
  const range = maxCost - minCost || 1;

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        Date Matrix
      </h4>
      <div className="overflow-x-auto">
        <div className="flex gap-2 pb-2">
          {matrix.map((entry) => {
            const ratio = (entry.combined_total - minCost) / range;
            let bgClass = "bg-emerald-100 border-emerald-200";
            if (ratio > 0.66) {
              bgClass = "bg-red-100 border-red-200";
            } else if (ratio > 0.33) {
              bgClass = "bg-amber-100 border-amber-200";
            }

            const date = new Date(entry.departure_date + "T12:00:00");
            const dayName = date.toLocaleDateString("en-US", { weekday: "short" });
            const dayNum = date.getDate();
            const month = date.toLocaleDateString("en-US", { month: "short" });

            return (
              <div
                key={entry.departure_date}
                className={`flex flex-col items-center p-2 rounded-lg border min-w-[90px] ${bgClass} ${
                  entry.is_preferred ? "ring-2 ring-blue-500 ring-offset-1" : ""
                }`}
              >
                <span className="text-[10px] opacity-70">{dayName}</span>
                <span className="text-xs opacity-70">{month} {dayNum}</span>
                <span className="text-sm font-bold mt-1">
                  ${Math.round(entry.combined_total)}
                </span>
                <div className="text-[9px] text-muted-foreground mt-0.5 space-y-0">
                  <span className="block">F: ${Math.round(entry.flight_cost)}</span>
                  <span className="block">H: ${Math.round(entry.hotel_total)}</span>
                </div>
                {entry.events.length > 0 && (
                  <span className="mt-0.5 text-[8px] text-amber-600 truncate max-w-[80px]" title={entry.events.join(", ")}>
                    {entry.events.length} event(s)
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
