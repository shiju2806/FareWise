import { useEffect, useMemo, useState, useCallback } from "react";
import type { PriceCalendar } from "@/types/search";
import { usePriceIntelStore } from "@/stores/priceIntelStore";
import { MonthCalendarCell } from "./MonthCalendarCell";

const DAY_NAMES = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const PERCENTILE_STYLES: Record<string, string> = {
  excellent: "text-emerald-600 font-semibold",
  good: "text-emerald-600",
  average: "text-amber-600",
  high: "text-red-600",
};

interface Props {
  legId: string;
  preferredDate: string;
  initialCalendar: PriceCalendar;
  selectedDate: string | null;
  onDateSelect: (date: string) => void;
}

/** Get year/month for the Nth month offset from a base. */
function offsetMonth(year: number, month: number, delta: number) {
  let m = month + delta;
  let y = year;
  while (m > 12) { m -= 12; y++; }
  while (m < 1) { m += 12; y--; }
  return { year: y, month: m };
}

export function MonthCalendar({
  legId,
  preferredDate,
  initialCalendar,
  selectedDate,
  onDateSelect,
}: Props) {
  const prefDate = new Date(preferredDate + "T00:00:00");
  const [viewYear, setViewYear] = useState(prefDate.getFullYear());
  const [viewMonth, setViewMonth] = useState(prefDate.getMonth() + 1);
  const [expanded, setExpanded] = useState(false);

  // Second month
  const second = offsetMonth(viewYear, viewMonth, 1);

  const {
    monthData, monthLoading, fetchMonthCalendar,
    priceContext, priceContextLoading, fetchPriceContext,
  } = usePriceIntelStore();

  // Fetch months (second only when expanded)
  useEffect(() => {
    fetchMonthCalendar(legId, viewYear, viewMonth);
    if (expanded) {
      fetchMonthCalendar(legId, second.year, second.month);
    }
  }, [legId, viewYear, viewMonth, second.year, second.month, expanded, fetchMonthCalendar]);

  // Fetch price context when a date is selected
  useEffect(() => {
    if (selectedDate) {
      fetchPriceContext(legId, selectedDate);
    }
  }, [selectedDate, legId, fetchPriceContext]);

  const contextKey = selectedDate ? `${legId}:${selectedDate}` : "";
  const context = contextKey ? priceContext[contextKey] : undefined;
  const contextLoading = contextKey ? priceContextLoading[contextKey] : false;

  /** Merge initial search data + store data for a given year/month. */
  const getMergedDates = useCallback(
    (y: number, m: number) => {
      const dates: Record<string, { min_price: number; has_direct: boolean; option_count: number }> = {};
      const mp = `${y}-${String(m).padStart(2, "0")}`;
      const key = `${legId}:${mp}`;
      const stored = monthData[key];

      // Initial search data first
      for (const [dateStr, data] of Object.entries(initialCalendar.dates)) {
        if (dateStr.startsWith(mp)) {
          dates[dateStr] = {
            min_price: data.min_price,
            has_direct: data.has_direct ?? false,
            option_count: data.option_count,
          };
        }
      }

      // Merge lazy-loaded data
      if (stored?.dates) {
        for (const [dateStr, data] of Object.entries(stored.dates)) {
          if (!(dateStr in dates)) {
            dates[dateStr] = {
              min_price: data.min_price,
              has_direct: data.has_direct ?? false,
              option_count: data.option_count,
            };
          }
        }
      }

      return dates;
    },
    [initialCalendar.dates, monthData, legId]
  );

  const mergedLeft = useMemo(() => getMergedDates(viewYear, viewMonth), [getMergedDates, viewYear, viewMonth]);
  const mergedRight = useMemo(() => getMergedDates(second.year, second.month), [getMergedDates, second.year, second.month]);

  // Compute quartiles across visible months for consistent coloring
  const allMerged = useMemo(() => expanded ? { ...mergedLeft, ...mergedRight } : { ...mergedLeft }, [mergedLeft, mergedRight, expanded]);

  const priceQuartiles = useMemo(() => {
    const prices = Object.values(allMerged)
      .map((d) => d.min_price)
      .filter((p) => p > 0)
      .sort((a, b) => a - b);

    if (prices.length === 0) return { q1: 0, q3: 0 };
    const q1 = prices[Math.floor(prices.length * 0.25)];
    const q3 = prices[Math.floor(prices.length * 0.75)];
    return { q1, q3 };
  }, [allMerged]);

  function getQuartile(price: number | null): "cheap" | "mid" | "expensive" | "none" {
    if (price === null || price === 0) return "none";
    if (price <= priceQuartiles.q1) return "cheap";
    if (price >= priceQuartiles.q3) return "expensive";
    return "mid";
  }

  function navigateMonth(delta: number) {
    const next = offsetMonth(viewYear, viewMonth, delta);
    setViewYear(next.year);
    setViewMonth(next.month);
  }

  // Stats across both months
  const allPrices = Object.values(allMerged).map((d) => d.min_price).filter((p) => p > 0);
  let cheapestDate: string | null = null;
  let cheapestPrice = Infinity;
  for (const [dateStr, data] of Object.entries(allMerged)) {
    if (data.min_price > 0 && data.min_price < cheapestPrice) {
      cheapestPrice = data.min_price;
      cheapestDate = dateStr;
    }
  }
  const avgPrice = allPrices.length > 0
    ? Math.round(allPrices.reduce((a, b) => a + b, 0) / allPrices.length)
    : 0;
  const directCount = Object.values(allMerged).filter((d) => d.has_direct).length;
  const hasData = allPrices.length > 0;

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const leftLoading = monthLoading[`${legId}:${viewYear}-${String(viewMonth).padStart(2, "0")}`] ?? false;
  const rightLoading = monthLoading[`${legId}:${second.year}-${String(second.month).padStart(2, "0")}`] ?? false;

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Price Calendar</h3>
        {initialCalendar.savings_if_flexible > 0 && (
          <span className="text-xs text-emerald-600 font-medium">
            Save ${Math.round(initialCalendar.savings_if_flexible)} with flexible dates
          </span>
        )}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => navigateMonth(expanded ? -2 : -1)}
          className="px-2 py-1 rounded hover:bg-muted text-sm"
        >
          &larr;
        </button>
        <span className="text-sm font-medium">
          {expanded
            ? `${MONTH_SHORT[viewMonth - 1]} \u2013 ${MONTH_SHORT[second.month - 1]} ${second.year !== viewYear ? `${viewYear}/${second.year}` : viewYear}`
            : `${MONTH_NAMES[viewMonth - 1]} ${viewYear}`
          }
        </span>
        <button
          type="button"
          onClick={() => navigateMonth(expanded ? 2 : 1)}
          className="px-2 py-1 rounded hover:bg-muted text-sm"
        >
          &rarr;
        </button>
      </div>

      {/* Month grid(s) */}
      <div className={expanded ? "grid grid-cols-2 gap-4" : ""}>
        <SingleMonthGrid
          year={viewYear}
          month={viewMonth}
          mergedDates={mergedLeft}
          isLoading={leftLoading}
          today={today}
          preferredDate={preferredDate}
          cheapestDate={cheapestDate}
          selectedDate={selectedDate}
          getQuartile={getQuartile}
          onDateSelect={onDateSelect}
        />
        {expanded && (
          <SingleMonthGrid
            year={second.year}
            month={second.month}
            mergedDates={mergedRight}
            isLoading={rightLoading}
            today={today}
            preferredDate={preferredDate}
            cheapestDate={cheapestDate}
            selectedDate={selectedDate}
            getQuartile={getQuartile}
            onDateSelect={onDateSelect}
          />
        )}
      </div>

      {/* Expand / collapse toggle */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="text-[10px] text-primary hover:underline w-full text-center"
      >
        {expanded ? "Show one month" : "Show next month"}
      </button>

      {/* Loading */}
      {(leftLoading || rightLoading) && !hasData && (
        <div className="text-center py-2 text-xs text-muted-foreground animate-pulse">
          Loading prices...
        </div>
      )}

      {/* Price Context — shown when a date is selected */}
      {selectedDate && (contextLoading || (context?.available && context.historical)) && (
        <div className="rounded-md border border-border bg-muted/30 px-3 py-2 space-y-1">
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
            Market Price Range &middot; {selectedDate}
          </p>
          {contextLoading ? (
            <div className="h-3 w-48 bg-muted animate-pulse rounded" />
          ) : context?.available && context.historical ? (
            <>
              <div className="flex items-center gap-1.5 text-[9px]">
                <span className="shrink-0 w-8 text-right">${Math.round(context.historical.min)}</span>
                <div className="flex-1 h-2.5 bg-gradient-to-r from-emerald-200 via-amber-200 to-red-200 rounded-full relative">
                  {context.percentile != null && (
                    <div
                      className="absolute top-[-1px] w-1.5 h-3.5 bg-primary rounded-sm"
                      style={{ left: `${Math.max(2, Math.min(98, context.percentile))}%` }}
                      title={context.current_price ? `Your price: $${Math.round(context.current_price)}` : undefined}
                    />
                  )}
                </div>
                <span className="shrink-0 w-8">${Math.round(context.historical.max)}</span>
              </div>
              {context.percentile_label && (
                <p className="text-[10px]">
                  <span className={PERCENTILE_STYLES[context.percentile_label] || ""}>
                    {context.percentile_label.charAt(0).toUpperCase() + context.percentile_label.slice(1)} price
                  </span>
                  {" "}
                  <span className="text-muted-foreground">
                    ({context.percentile}th percentile
                    {context.current_price ? ` at $${Math.round(context.current_price)}` : ""})
                  </span>
                </p>
              )}
            </>
          ) : null}
        </div>
      )}

      {/* Legend + stats */}
      {hasData && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-[9px] text-muted-foreground">
          <div className="flex gap-2">
            <span className="flex items-center gap-0.5">
              <span className="w-2.5 h-2.5 rounded bg-emerald-50 border border-emerald-300" />
              Cheap
            </span>
            <span className="flex items-center gap-0.5">
              <span className="w-2.5 h-2.5 rounded bg-amber-50 border border-amber-300" />
              Avg
            </span>
            <span className="flex items-center gap-0.5">
              <span className="w-2.5 h-2.5 rounded bg-red-50 border border-red-300" />
              Exp
            </span>
            <span className="flex items-center gap-0.5">
              <span className="text-[8px]">{"\u25CF"}</span> Direct
            </span>
            <span className="flex items-center gap-0.5">
              <span className="text-[8px]">{"\u2715"}</span> Connect
            </span>
          </div>
          <div className="flex gap-3">
            {cheapestPrice < Infinity && (
              <span>
                Low: <span className="font-medium text-emerald-600">${Math.round(cheapestPrice)}</span>
              </span>
            )}
            {avgPrice > 0 && <span>Avg: ${avgPrice}</span>}
            <span>{directCount} direct</span>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Single-month grid (used twice for the 2-month layout)              */
/* ------------------------------------------------------------------ */

interface GridProps {
  year: number;
  month: number;
  mergedDates: Record<string, { min_price: number; has_direct: boolean; option_count: number }>;
  isLoading: boolean;
  today: Date;
  preferredDate: string;
  cheapestDate: string | null;
  selectedDate: string | null;
  getQuartile: (price: number | null) => "cheap" | "mid" | "expensive" | "none";
  onDateSelect: (date: string) => void;
}

function SingleMonthGrid({
  year,
  month,
  mergedDates,
  isLoading,
  today,
  preferredDate,
  cheapestDate,
  selectedDate,
  getQuartile,
  onDateSelect,
}: GridProps) {
  const firstDay = new Date(year, month - 1, 1);
  const daysInMonth = new Date(year, month, 0).getDate();
  let startDow = firstDay.getDay() - 1;
  if (startDow < 0) startDow = 6;

  const cells: { day: number; dateStr: string }[] = [];
  for (let i = 0; i < startDow; i++) {
    cells.push({ day: 0, dateStr: "" });
  }
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    cells.push({ day: d, dateStr });
  }
  while (cells.length % 7 !== 0) {
    cells.push({ day: 0, dateStr: "" });
  }

  return (
    <div>
      <p className="text-xs font-semibold text-center mb-1">
        {MONTH_NAMES[month - 1]} {year}
      </p>
      <div className="grid grid-cols-7 gap-0.5">
        {DAY_NAMES.map((d) => (
          <div key={d} className="text-center text-[8px] font-medium text-muted-foreground py-0.5">
            {d}
          </div>
        ))}

        {cells.map((cell, i) => {
          const data = cell.dateStr ? mergedDates[cell.dateStr] : null;
          const cellDate = cell.dateStr ? new Date(cell.dateStr + "T00:00:00") : null;
          const isPast = cellDate ? cellDate < today : false;
          const cellIsLoading = cell.day > 0 && !isPast && !data && isLoading;

          return (
            <MonthCalendarCell
              key={i}
              day={cell.day}
              dateStr={cell.dateStr}
              price={data?.min_price ?? null}
              hasDirect={data?.has_direct ?? false}
              isPreferred={cell.dateStr === preferredDate}
              isCheapest={cell.dateStr === cheapestDate}
              isSelected={cell.dateStr === selectedDate}
              isPast={isPast}
              isLoading={cellIsLoading}
              quartile={getQuartile(data?.min_price ?? null)}
              onClick={onDateSelect}
            />
          );
        })}
      </div>
    </div>
  );
}
