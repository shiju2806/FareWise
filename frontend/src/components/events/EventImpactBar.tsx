interface Props {
  level: "low" | "medium" | "high" | "very_high";
}

const barConfig: Record<string, { width: string; color: string; label: string }> = {
  low: { width: "w-1/4", color: "bg-gray-300", label: "Low" },
  medium: { width: "w-2/4", color: "bg-amber-400", label: "Medium" },
  high: { width: "w-3/4", color: "bg-orange-500", label: "High" },
  very_high: { width: "w-full", color: "bg-red-500", label: "Very High" },
};

export function EventImpactBar({ level }: Props) {
  const config = barConfig[level] || barConfig.low;

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${config.width} ${config.color}`} />
      </div>
      <span className="text-[10px] text-muted-foreground whitespace-nowrap">
        {config.label}
      </span>
    </div>
  );
}
