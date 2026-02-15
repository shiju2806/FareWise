import { useEffect, useState, useRef } from "react";
import { usePriceIntelStore } from "@/stores/priceIntelStore";
import type { PriceAdvice } from "@/types/search";

interface Props {
  legId: string;
}

/* ── Style maps ── */

const RECOMMENDATION_STYLES: Record<
  string,
  { bg: string; text: string; border: string; label: string }
> = {
  book: {
    bg: "bg-emerald-100",
    text: "text-emerald-800",
    border: "border-emerald-300",
    label: "Book Now",
  },
  wait: {
    bg: "bg-amber-100",
    text: "text-amber-800",
    border: "border-amber-300",
    label: "Wait",
  },
  watch: {
    bg: "bg-blue-100",
    text: "text-blue-800",
    border: "border-blue-300",
    label: "Watch",
  },
};

const IMPACT_ICONS: Record<string, { icon: string; color: string }> = {
  positive: { icon: "\u2713", color: "text-emerald-600" },
  negative: { icon: "\u26A0", color: "text-amber-600" },
  neutral: { icon: "\u2014", color: "text-muted-foreground" },
};

/* ── Chevron SVG ── */

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`transition-transform duration-200 ${open ? "rotate-180" : "rotate-0"}`}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

/* ── Compact loading skeleton (single-line shimmer) ── */

function AdvisorSkeleton() {
  return (
    <div className="rounded-lg border border-border h-10 flex items-center px-3 gap-3 animate-pulse">
      <div className="h-5 w-16 bg-muted rounded-full shrink-0" />
      <div className="flex-1 h-3 bg-muted rounded" />
      <div className="h-5 w-14 bg-muted rounded shrink-0" />
    </div>
  );
}

/* ── Main component ── */

export function PriceAdvisorPanel({ legId }: Props) {
  const { advice, adviceLoading, fetchAdvice } = usePriceIntelStore();
  const [expanded, setExpanded] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = useState(0);

  useEffect(() => {
    fetchAdvice(legId);
  }, [legId, fetchAdvice]);

  // Measure content height for smooth animation
  useEffect(() => {
    if (contentRef.current) {
      setContentHeight(contentRef.current.scrollHeight);
    }
  }, [expanded, advice[legId]]);

  const loading = adviceLoading[legId];
  const data: PriceAdvice | undefined = advice[legId];

  if (loading) return <AdvisorSkeleton />;
  if (!data) return null;
  if (data.source === "disabled") return null;

  const recStyle = RECOMMENDATION_STYLES[data.recommendation] || RECOMMENDATION_STYLES.watch;

  return (
    <div className={`rounded-lg border ${recStyle.border} overflow-hidden`}>
      {/* ── Collapsed banner row ── */}
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className={`w-full flex items-center gap-2.5 px-3 h-10 ${recStyle.bg} hover:opacity-90 transition-opacity cursor-pointer`}
      >
        {/* Recommendation badge */}
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${recStyle.border} ${recStyle.bg} ${recStyle.text} shrink-0`}
        >
          {recStyle.label}
        </span>

        {/* Headline (truncated to one line) */}
        <span className="flex-1 text-sm font-medium text-left truncate">
          {data.headline}
        </span>

        {/* Confidence badge */}
        {data.confidence > 0 && (
          <span className="text-[10px] text-muted-foreground shrink-0 hidden sm:inline">
            {Math.round(data.confidence * 100)}% conf.
          </span>
        )}

        {/* Toggle button */}
        <span className="flex items-center gap-1 text-xs text-muted-foreground shrink-0">
          <span className="hidden sm:inline">{expanded ? "Hide" : "Details"}</span>
          <ChevronIcon open={expanded} />
        </span>
      </button>

      {/* ── Expandable detail section ── */}
      <div
        style={{
          maxHeight: expanded ? `${contentHeight}px` : "0px",
        }}
        className="transition-[max-height] duration-300 ease-in-out overflow-hidden"
      >
        <div ref={contentRef} className="px-3 py-3 space-y-3 bg-background">
          {/* Analysis */}
          {data.analysis && (
            <p className="text-xs text-muted-foreground leading-relaxed">
              {data.analysis}
            </p>
          )}

          {/* Savings potential */}
          {data.savings_potential && (
            <p className="text-xs font-medium">
              Savings potential: <span className="text-emerald-700">{data.savings_potential}</span>
            </p>
          )}

          {/* Factors */}
          {data.factors.length > 0 && (
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Key Factors
              </p>
              {data.factors.slice(0, 5).map((factor, i) => {
                const impactStyle = IMPACT_ICONS[factor.impact] || IMPACT_ICONS.neutral;
                return (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <span
                      className={`${impactStyle.color} font-bold mt-0.5 shrink-0 w-4 text-center`}
                    >
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
            <div className="rounded bg-muted/50 px-3 py-2 text-xs">
              <span className="font-medium">Timing: </span>
              <span className="text-muted-foreground">{data.timing_advice}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
