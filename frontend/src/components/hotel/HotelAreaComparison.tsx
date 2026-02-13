import type { AreaComparison } from "@/types/hotel";

interface Props {
  areas: AreaComparison[];
  onAreaClick?: (area: string) => void;
}

export function HotelAreaComparison({ areas, onAreaClick }: Props) {
  if (areas.length === 0) return null;

  const maxRate = Math.max(...areas.map((a) => a.avg_rate));

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">Area Comparison</h3>
      <div className="space-y-1.5">
        {areas.map((area) => {
          const barWidth = (area.avg_rate / maxRate) * 100;
          return (
            <button
              key={area.area}
              type="button"
              onClick={() => onAreaClick?.(area.area)}
              className="w-full flex items-center gap-3 text-xs hover:bg-accent/30 rounded p-1 transition-colors"
            >
              <span className="w-32 text-left truncate font-medium">
                {area.area}
              </span>
              <div className="flex-1 h-4 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary/30 rounded-full"
                  style={{ width: `${barWidth}%` }}
                />
              </div>
              <span className="w-20 text-right text-muted-foreground">
                ${Math.round(area.avg_rate)}/night
              </span>
              <span className="w-14 text-right text-muted-foreground">
                {area.option_count} opts
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
