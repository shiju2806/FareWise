import { useEffect } from "react";
import { usePriceIntelStore } from "@/stores/priceIntelStore";
import type { PriceAdvice } from "@/types/search";

interface Props {
  legId: string;
}

const RECOMMENDATION_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  book: {
    bg: "bg-emerald-100 border-emerald-300",
    text: "text-emerald-800",
    label: "Book Now",
  },
  wait: {
    bg: "bg-amber-100 border-amber-300",
    text: "text-amber-800",
    label: "Wait",
  },
  watch: {
    bg: "bg-blue-100 border-blue-300",
    text: "text-blue-800",
    label: "Watch",
  },
};

const IMPACT_ICONS: Record<string, { icon: string; color: string }> = {
  positive: { icon: "\u2713", color: "text-emerald-600" },
  negative: { icon: "\u26A0", color: "text-amber-600" },
  neutral: { icon: "\u2014", color: "text-muted-foreground" },
};

function AdvisorSkeleton() {
  return (
    <div className="rounded-lg border border-border p-4 space-y-3 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="h-6 w-20 bg-muted rounded-full" />
        <div className="flex-1 h-4 bg-muted rounded" />
      </div>
      <div className="h-3 w-full bg-muted rounded" />
      <div className="h-3 w-3/4 bg-muted rounded" />
      <div className="space-y-1.5 pt-1">
        <div className="h-3 w-48 bg-muted rounded" />
        <div className="h-3 w-44 bg-muted rounded" />
      </div>
    </div>
  );
}

export function PriceAdvisorPanel({ legId }: Props) {
  const { advice, adviceLoading, fetchAdvice } = usePriceIntelStore();

  useEffect(() => {
    fetchAdvice(legId);
  }, [legId, fetchAdvice]);

  const loading = adviceLoading[legId];
  const data: PriceAdvice | undefined = advice[legId];

  if (loading) return <AdvisorSkeleton />;
  if (!data) return null;
  if (data.source === "disabled") return null;

  const recStyle = RECOMMENDATION_STYLES[data.recommendation] || RECOMMENDATION_STYLES.watch;

  return (
    <div className="rounded-lg border border-border p-4 space-y-3">
      {/* Header: badge + headline */}
      <div className="flex items-start gap-3">
        <span
          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${recStyle.bg} ${recStyle.text} shrink-0`}
        >
          {recStyle.label}
        </span>
        <p className="text-sm font-medium leading-snug">{data.headline}</p>
      </div>

      {/* Analysis */}
      <p className="text-xs text-muted-foreground leading-relaxed">
        {data.analysis}
      </p>

      {/* Factors — max 4 */}
      {data.factors.length > 0 && (
        <div className="space-y-1">
          {data.factors.slice(0, 4).map((factor, i) => {
            const impactStyle = IMPACT_ICONS[factor.impact] || IMPACT_ICONS.neutral;
            return (
              <div key={i} className="flex items-start gap-2 text-xs">
                <span className={`${impactStyle.color} font-bold mt-0.5 shrink-0 w-4 text-center`}>
                  {impactStyle.icon}
                </span>
                <div>
                  <span className="font-medium">{factor.name}:</span>{" "}
                  <span className="text-muted-foreground">{factor.detail}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Timing advice */}
      {data.timing_advice && (
        <div className="rounded bg-muted/50 px-3 py-1.5 text-xs">
          <span className="font-medium">Timing: </span>
          <span className="text-muted-foreground">{data.timing_advice}</span>
        </div>
      )}
    </div>
  );
}
