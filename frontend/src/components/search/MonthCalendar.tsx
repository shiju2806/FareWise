import { useEffect, useMemo, useState, useCallback } from "react";
import type { PriceCalendar } from "@/types/search";
import type { FlightOption } from "@/types/flight";
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


interface Props {
  legId: string;
  preferredDate: string;
  initialCalendar: PriceCalendar;
  selectedDate: string | null;
  onDateSelect: (date: string) => void;
  onMonthChange?: (year: number, month: number) => void;
  /** When exactly one airline is filtered, show that airline's prices */
  activeAirline?: string | null;
  /** All flight options from search results (for airline-specific pricing) */
  allOptions?: FlightOption[];
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
  onMonthChange,
  activeAirline,
  allOptions,
}: Props) {
  const prefDate = new Date(preferredDate + "T00:00:00");
  const [viewYear, setViewYear] = useState(prefDate.getFullYear());
  const [viewMonth, setViewMonth] = useState(prefDate.getMonth() + 1);
  const [expanded, setExpanded] = useState(false);

  // Second month
  const second = offsetMonth(viewYear, viewMonth, 1);

  const {
    monthData, monthLoading, fetchMonthCalendar,
    matrixData, fetchMonthMatrix,
  } = usePriceIntelStore();

  // Fetch months (second only when expanded)
  useEffect(() => {
    fetchMonthCalendar(legId, viewYear, viewMonth);
    if (expanded) {
      fetchMonthCalendar(legId, second.year, second.month);
    }
  }, [legId, viewYear, viewMonth, second.year, second.month, expanded, fetchMonthCalendar]);

  // When airline filter is active, ensure matrix data is loaded for visible months
  useEffect(() => {
    if (activeAirline) {
      fetchMonthMatrix(legId, viewYear, viewMonth);
      if (expanded) {
        fetchMonthMatrix(legId, second.year, second.month);
      }
    }
  }, [activeAirline, legId, viewYear, viewMonth, second.year, second.month, expanded, fetchMonthMatrix]);

  /** Merge initial search data + store data for a given year/month.
   *  When activeAirline is set, shows that airline's prices instead of cheapest-overall. */
  const getMergedDates = useCallback(
    (y: number, m: number) => {
      const dates: Record<string, { min_price: number; has_direct: boolean; option_count: number }> = {};
      const mp = `${y}-${String(m).padStart(2, "0")}`;
      const key = `${legId}:${mp}`;

      if (activeAirline && allOptions) {
        // Airline-specific: compute from allOptions (search results for this airline)
        for (const f of allOptions) {
          const d = f.departure_time?.substring(0, 10);
          if (!d?.startsWith(mp) || f.airline_name !== activeAirline) continue;
          if (!dates[d] || f.price < dates[d].min_price) {
            dates[d] = { min_price: f.price, has_direct: f.stops === 0, option_count: 1 };
          } else {
            dates[d].option_count++;
            if (f.stops === 0) dates[d].has_direct = true;
          }
        }
        // Supplement from matrixData for dates outside the search window
        const matrixEntries = matrixData[key];
        if (matrixEntries) {
          for (const entry of matrixEntries) {
            if (entry.airline_name !== activeAirline) continue;
            if (!(entry.date in dates)) {
              dates[entry.date] = { min_price: entry.price, has_direct: entry.stops === 0, option_count: 1 };
            }
          }
        }
      } else {
        // Default: cheapest overall (current behavior)
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
      }

      return dates;
    },
    [initialCalendar.dates, monthData, matrixData, legId, activeAirline, allOptions]
  );

  const mergedLeft = useMemo(() => getMergedDates(viewYear, viewMonth), [getMergedDates, viewYear, viewMonth]);
  const mergedRight = useMemo(() => getMergedDates(second.year, second.month), [getMergedDates, second.year, second.month]);

  // Compute min/max across visible months for continuous heat map
  const allMerged = useMemo(() => expanded ? { ...mergedLeft, ...mergedRight } : { ...mergedLeft }, [mergedLeft, mergedRight, expanded]);

  const priceRange = useMemo(() => {
    const prices = Object.values(allMerged)
      .map((d) => d.min_price)
      .filter((p) => p > 0);

    if (prices.length === 0) return { min: 0, max: 0 };
    return { min: Math.min(...prices), max: Math.max(...prices) };
  }, [allMerged]);

  /** Continuous ratio: 0.0 = cheapest, 1.0 = most expensive */
  function getPriceRatio(price: number | null): number {
    if (price === null || price === 0) return 0.5;
    const { min, max } = priceRange;
    if (max === min) return 0.5;
    return (price - min) / (max - min);
  }

  function navigateMonth(delta: number) {
    const next = offsetMonth(viewYear, viewMonth, delta);
    setViewYear(next.year);
    setViewMonth(next.month);
    onMonthChange?.(next.year, next.month);
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
        <h3 className="text-sm font-semibold">
          {activeAirline ? `${activeAirline} Prices` : "Price Calendar"}
        </h3>
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
          getPriceRatio={getPriceRatio}
          onDateSelect={onDateSelect}
          showHeader={expanded}
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
            getPriceRatio={getPriceRatio}
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

      {/* Legend + stats */}
      {hasData && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-[9px] text-muted-foreground">
          <div className="flex items-center gap-1">
            {/* Gradient legend */}
            <span className="font-medium">Low</span>
            <div className="flex h-2.5">
              <span className="w-3 rounded-l" style={{ backgroundColor: "rgb(5, 150, 105)" }} />
              <span className="w-3" style={{ backgroundColor: "rgb(16, 185, 129)" }} />
              <span className="w-3" style={{ backgroundColor: "rgb(110, 231, 183)" }} />
              <span className="w-3" style={{ backgroundColor: "rgb(254, 243, 199)" }} />
              <span className="w-3" style={{ backgroundColor: "rgb(253, 186, 116)" }} />
              <span className="w-3" style={{ backgroundColor: "rgb(248, 113, 113)" }} />
              <span className="w-3 rounded-r" style={{ backgroundColor: "rgb(220, 38, 38)" }} />
            </div>
            <span className="font-medium">High</span>
            <span className="mx-1 opacity-40">|</span>
            <span className="flex items-center gap-0.5">
              <span className="text-[8px]">{"\u25CF"}</span> Direct
            </span>
            <span className="flex items-center gap-0.5">
              <span className="text-[8px]">{"\u2715"}</span> Connect
            </span>
            <span className="flex items-center gap-0.5">
              <span className="w-2.5 h-2.5 rounded-sm ring-1.5 ring-blue-500 inline-block" /> Preferred
            </span>
            <span className="flex items-center gap-0.5">
              <span className="text-[6px]">&#9733;</span> Cheapest
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
  getPriceRatio: (price: number | null) => number;
  onDateSelect: (date: string) => void;
  showHeader?: boolean;
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
  getPriceRatio,
  onDateSelect,
  showHeader = true,
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
      {showHeader && (
        <p className="text-xs font-semibold text-center mb-1">
          {MONTH_NAMES[month - 1]} {year}
        </p>
      )}
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
              isPreferred={cell.dateStr === preferredDate && (!selectedDate || selectedDate === preferredDate)}
              isCheapest={cell.dateStr === cheapestDate}
              isSelected={cell.dateStr === selectedDate}
              isPast={isPast}
              isLoading={cellIsLoading}
              priceRatio={getPriceRatio(data?.min_price ?? null)}
              onClick={onDateSelect}
            />
          );
        })}
      </div>
    </div>
  );
}
