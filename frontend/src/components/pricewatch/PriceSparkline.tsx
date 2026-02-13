import type { PriceHistoryPoint } from "@/types/priceWatch";

interface Props {
  history: PriceHistoryPoint[];
  trend: "up" | "down" | "flat";
  width?: number;
  height?: number;
}

export function PriceSparkline({
  history,
  trend,
  width = 120,
  height = 32,
}: Props) {
  if (history.length < 2) {
    return (
      <div
        className="flex items-center justify-center text-xs text-muted-foreground"
        style={{ width, height }}
      >
        No data
      </div>
    );
  }

  const prices = history.map((h) => h.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;

  const padding = 2;
  const innerW = width - padding * 2;
  const innerH = height - padding * 2;

  const points = prices.map((p, i) => {
    const x = padding + (i / (prices.length - 1)) * innerW;
    const y = padding + innerH - ((p - min) / range) * innerH;
    return `${x},${y}`;
  });

  const strokeColor =
    trend === "down"
      ? "rgb(34, 197, 94)"
      : trend === "up"
        ? "rgb(239, 68, 68)"
        : "rgb(156, 163, 175)";

  return (
    <svg width={width} height={height} className="inline-block">
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Last point dot */}
      {points.length > 0 && (
        <circle
          cx={points[points.length - 1].split(",")[0]}
          cy={points[points.length - 1].split(",")[1]}
          r="2"
          fill={strokeColor}
        />
      )}
    </svg>
  );
}
