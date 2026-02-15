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
  quartile: "cheap" | "mid" | "expensive" | "none";
  onClick: (date: string) => void;
}

/** Format price compactly: $1.5k for >=1000, $843 for <1000 */
function fmtPrice(price: number): string {
  if (price >= 1000) {
    const k = price / 1000;
    return `$${k % 1 === 0 ? k.toFixed(0) : k.toFixed(1)}k`;
  }
  return `$${Math.round(price)}`;
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
  quartile,
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

  const bgColor = {
    cheap: "bg-emerald-50 hover:bg-emerald-100",
    mid: "bg-amber-50 hover:bg-amber-100",
    expensive: "bg-red-50 hover:bg-red-100",
    none: "bg-muted/20 hover:bg-muted/40",
  }[quartile];

  const borderClass = isSelected
    ? "ring-2 ring-primary"
    : isPreferred
    ? "ring-2 ring-blue-500"
    : isCheapest
    ? "ring-2 ring-emerald-500"
    : "border border-border/50";

  return (
    <button
      type="button"
      onClick={() => price !== null && onClick(dateStr)}
      disabled={price === null}
      className={`h-8 rounded flex flex-col items-center justify-center transition-all cursor-pointer gap-0 ${bgColor} ${borderClass} ${
        price === null ? "opacity-40 cursor-not-allowed" : ""
      }`}
    >
      <span className={`text-[7px] leading-none ${isPreferred ? "font-bold text-blue-700" : "text-muted-foreground"}`}>
        {day}
      </span>
      {price !== null ? (
        <span className="font-semibold text-[9px] leading-tight">
          {fmtPrice(price)}{" "}
          <span className="text-[6px] text-muted-foreground">
            {hasDirect ? "\u25CF" : "\u2715"}
          </span>
        </span>
      ) : (
        <span className="text-[8px] text-muted-foreground">--</span>
      )}
    </button>
  );
}
