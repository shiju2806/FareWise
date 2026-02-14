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
    // Empty cell for padding
    return <div className="w-full aspect-square" />;
  }

  if (isPast) {
    return (
      <div className="w-full aspect-square rounded-md bg-muted/30 flex flex-col items-center justify-center text-muted-foreground/40 text-xs">
        <span>{day}</span>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="w-full aspect-square rounded-md bg-muted animate-pulse flex items-center justify-center text-xs text-muted-foreground">
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
      className={`w-full aspect-square rounded-md flex flex-col items-center justify-center gap-0.5 transition-all text-xs cursor-pointer ${bgColor} ${borderClass} ${
        price === null ? "opacity-40 cursor-not-allowed" : ""
      }`}
    >
      <span className={`text-[10px] ${isPreferred ? "font-bold text-blue-700" : "text-muted-foreground"}`}>
        {day}
      </span>
      {price !== null ? (
        <>
          <span className="font-semibold text-[11px] leading-tight">
            ${Math.round(price)}
          </span>
          <span className="text-[9px] text-muted-foreground leading-tight">
            {hasDirect ? "\u25CF direct" : "\u2715 connect"}
          </span>
        </>
      ) : (
        <span className="text-[9px] text-muted-foreground">--</span>
      )}
    </button>
  );
}
