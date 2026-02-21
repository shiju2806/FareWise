import { formatCompactPrice as fmtPrice } from "@/lib/currency";

interface Props {
  day: number;
  dateStr: string;
  price: number | null;
  hasDirect: boolean;
  isPreferred: boolean;
  isCheapest: boolean;
  isSelected: boolean;
  isPast: boolean;
  isLoading: boolean;
  /** 0.0 (cheapest) → 1.0 (most expensive) for continuous heat map */
  priceRatio: number;
  onClick: (date: string) => void;
}

/** Continuous heat map: 0.0 = darkest green → 0.5 = neutral → 1.0 = darkest red */
function heatMapStyle(ratio: number): React.CSSProperties {
  if (ratio <= 0.15) return { backgroundColor: "rgb(5, 150, 105)" };        // emerald-600
  if (ratio <= 0.30) return { backgroundColor: "rgb(16, 185, 129)" };       // emerald-500
  if (ratio <= 0.45) return { backgroundColor: "rgb(110, 231, 183)" };      // emerald-300
  if (ratio <= 0.55) return { backgroundColor: "rgb(254, 243, 199)" };      // amber-100
  if (ratio <= 0.70) return { backgroundColor: "rgb(253, 186, 116)" };      // orange-300
  if (ratio <= 0.85) return { backgroundColor: "rgb(248, 113, 113)" };      // red-400
  return { backgroundColor: "rgb(220, 38, 38)" };                            // red-600
}

function heatMapTextClass(ratio: number): string {
  if (ratio <= 0.15 || ratio > 0.85) return "text-white";
  return "text-foreground";
}

export function MonthCalendarCell({
  day,
  dateStr,
  price,
  hasDirect,
  isPreferred,
  isCheapest,
  isSelected,
  isPast,
  isLoading,
  priceRatio,
  onClick,
}: Props) {
  if (day === 0) {
    return <div className="h-8" />;
  }

  if (isPast) {
    return (
      <div className="h-8 rounded bg-muted/30 flex items-center justify-center text-muted-foreground/40 text-[9px]">
        {day}
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="h-8 rounded bg-muted animate-pulse flex items-center justify-center text-[9px] text-muted-foreground">
        {day}
      </div>
    );
  }

  const style = price !== null ? heatMapStyle(priceRatio) : undefined;
  const textCls = price !== null ? heatMapTextClass(priceRatio) : "";

  // Ring styles: selected = primary, preferred = blue, both = primary
  const ringClass = isSelected
    ? "ring-2 ring-primary ring-offset-1"
    : isPreferred
      ? "ring-2 ring-blue-500 ring-offset-1"
      : "";

  return (
    <button
      type="button"
      onClick={() => price !== null && onClick(dateStr)}
      disabled={price === null}
      className={`h-9 rounded-md flex flex-col items-center justify-center transition-all cursor-pointer gap-0 relative ${
        price === null ? "bg-muted/20 opacity-40 cursor-not-allowed" : "hover:opacity-80"
      } ${ringClass}`}
      style={style}
    >
      {/* Cheapest date: small star/diamond indicator */}
      {isCheapest && !isSelected && (
        <span className="absolute top-0.5 left-0.5 text-[6px] leading-none text-white drop-shadow-sm">&#9733;</span>
      )}
      <span className={`text-[7px] leading-none ${textCls} ${isPreferred ? "font-bold" : "opacity-80"}`}>
        {day}
      </span>
      {price !== null ? (
        <span className={`font-semibold text-[9px] leading-tight ${textCls}`}>
          {fmtPrice(price)}{" "}
          <span className={`text-[6px] ${textCls} opacity-70`}>
            {hasDirect ? "\u25CF" : "\u2715"}
          </span>
        </span>
      ) : (
        <span className="text-[8px] text-muted-foreground">--</span>
      )}
    </button>
  );
}
