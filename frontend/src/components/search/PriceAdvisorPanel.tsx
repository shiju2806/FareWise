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

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 70 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-red-400";
  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-muted-foreground">{pct}%</span>
    </div>
  );
}

function AdvisorSkeleton() {
  return (
    <div className="rounded-lg border border-border p-4 space-y-4 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="h-7 w-24 bg-muted rounded-full" />
        <div className="flex-1 h-4 bg-muted rounded" />
      </div>
      <div className="h-3 w-full bg-muted rounded" />
      <div className="h-3 w-3/4 bg-muted rounded" />
      <div className="space-y-2 pt-2">
        <div className="h-3 w-56 bg-muted rounded" />
        <div className="h-3 w-48 bg-muted rounded" />
        <div className="h-3 w-52 bg-muted rounded" />
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
    <div className="rounded-lg border border-border p-4 space-y-4">
      {/* Header: badge + headline */}
      <div className="flex items-start gap-3">
        <span
          className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold border ${recStyle.bg} ${recStyle.text} shrink-0`}
        >
          {recStyle.label}
        </span>
        <p className="text-sm font-medium leading-snug">{data.headline}</p>
      </div>

      {/* Confidence bar */}
      <div>
        <span className="text-[10px] text-muted-foreground uppercase tracking-wide">
          Confidence
        </span>
        <ConfidenceBar value={data.confidence} />
      </div>

      {/* Analysis */}
      <p className="text-xs text-muted-foreground leading-relaxed">
        {data.analysis}
      </p>

      {/* Factors */}
      {data.factors.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-[10px] text-muted-foreground uppercase tracking-wide">
            Key Factors
          </span>
          {data.factors.map((factor, i) => {
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
        <div className="rounded-md bg-muted/50 px-3 py-2 text-xs">
          <span className="font-medium">Timing: </span>
          <span className="text-muted-foreground">{data.timing_advice}</span>
        </div>
      )}

      {/* Savings potential */}
      {data.savings_potential && (
        <p className="text-[10px] text-muted-foreground">
          {data.savings_potential}
        </p>
      )}

      {/* Source indicator */}
      <div className="text-[9px] text-muted-foreground/60 text-right">
        {data.source === "llm" ? "AI-powered analysis" : "Rule-based analysis"}
      </div>
    </div>
  );
}
