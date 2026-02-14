import { useEffect, useMemo, useState } from "react";
import type { PriceCalendar } from "@/types/search";
import { usePriceIntelStore } from "@/stores/priceIntelStore";
import { MonthCalendarCell } from "./MonthCalendarCell";

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

interface Props {
  legId: string;
  preferredDate: string;
  initialCalendar: PriceCalendar;
  selectedDate: string | null;
  onDateSelect: (date: string) => void;
}

export function MonthCalendar({
  legId,
  preferredDate,
  initialCalendar,
  selectedDate,
  onDateSelect,
}: Props) {
  // Parse preferred date to get initial month
  const prefDate = new Date(preferredDate + "T00:00:00");
  const [viewYear, setViewYear] = useState(prefDate.getFullYear());
  const [viewMonth, setViewMonth] = useState(prefDate.getMonth() + 1); // 1-based

  const { monthData, monthLoading, fetchMonthCalendar } = usePriceIntelStore();
  const monthKey = `${legId}:${viewYear}-${String(viewMonth).padStart(2, "0")}`;

  // Fetch month data when view changes
  useEffect(() => {
    fetchMonthCalendar(legId, viewYear, viewMonth);
  }, [legId, viewYear, viewMonth, fetchMonthCalendar]);

  const isLoading = monthLoading[monthKey] ?? false;
  const loadedMonth = monthData[monthKey];

  // Merge initial calendar data with loaded month data
  const mergedDates = useMemo(() => {
    const dates: Record<string, { min_price: number; has_direct: boolean; option_count: number }> = {};

    // Add initial search data
    for (const [dateStr, data] of Object.entries(initialCalendar.dates)) {
      if (dateStr.startsWith(`${viewYear}-${String(viewMonth).padStart(2, "0")}`)) {
        dates[dateStr] = {
          min_price: data.min_price,
          has_direct: data.has_direct ?? false,
          option_count: data.option_count,
        };
      }
    }

    // Overlay month data (takes priority since it may be more complete)
    if (loadedMonth?.dates) {
      for (const [dateStr, data] of Object.entries(loadedMonth.dates)) {
        dates[dateStr] = {
          min_price: data.min_price,
          has_direct: data.has_direct,
          option_count: data.option_count,
        };
      }
    }

    return dates;
  }, [initialCalendar.dates, loadedMonth, viewYear, viewMonth]);

  // Compute price quartiles for coloring
  const priceQuartiles = useMemo(() => {
    const prices = Object.values(mergedDates)
      .map((d) => d.min_price)
      .filter((p) => p > 0)
      .sort((a, b) => a - b);

    if (prices.length === 0) return { q1: 0, q3: 0 };
    const q1 = prices[Math.floor(prices.length * 0.25)];
    const q3 = prices[Math.floor(prices.length * 0.75)];
    return { q1, q3 };
  }, [mergedDates]);

  function getQuartile(price: number | null): "cheap" | "mid" | "expensive" | "none" {
    if (price === null || price === 0) return "none";
    if (price <= priceQuartiles.q1) return "cheap";
    if (price >= priceQuartiles.q3) return "expensive";
    return "mid";
  }

  // Build calendar grid
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const firstDay = new Date(viewYear, viewMonth - 1, 1);
  const daysInMonth = new Date(viewYear, viewMonth, 0).getDate();
  // Monday = 0, Sunday = 6 for our grid
  let startDow = firstDay.getDay() - 1;
  if (startDow < 0) startDow = 6;

  // Build rows
  const cells: { day: number; dateStr: string }[] = [];
  // Padding for first week
  for (let i = 0; i < startDow; i++) {
    cells.push({ day: 0, dateStr: "" });
  }
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${viewYear}-${String(viewMonth).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    cells.push({ day: d, dateStr });
  }
  // Pad to complete last row
  while (cells.length % 7 !== 0) {
    cells.push({ day: 0, dateStr: "" });
  }

  // Find cheapest date in current view
  let cheapestDate: string | null = null;
  let cheapestPrice = Infinity;
  for (const [dateStr, data] of Object.entries(mergedDates)) {
    if (data.min_price > 0 && data.min_price < cheapestPrice) {
      cheapestPrice = data.min_price;
      cheapestDate = dateStr;
    }
  }

  // Month stats
  const stats = loadedMonth?.month_stats;
  const allPrices = Object.values(mergedDates)
    .map((d) => d.min_price)
    .filter((p) => p > 0);
  const avgPrice = allPrices.length > 0
    ? Math.round(allPrices.reduce((a, b) => a + b, 0) / allPrices.length)
    : 0;
  const directCount = Object.values(mergedDates).filter((d) => d.has_direct).length;

  function navigateMonth(delta: number) {
    let newMonth = viewMonth + delta;
    let newYear = viewYear;
    if (newMonth > 12) {
      newMonth = 1;
      newYear++;
    } else if (newMonth < 1) {
      newMonth = 12;
      newYear--;
    }
    setViewYear(newYear);
    setViewMonth(newMonth);
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Price Calendar</h3>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {initialCalendar.savings_if_flexible > 0 && (
            <span className="text-emerald-600 font-medium">
              Save ${Math.round(initialCalendar.savings_if_flexible)} with flexible dates
            </span>
          )}
        </div>
      </div>

      {/* Month navigation */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => navigateMonth(-1)}
          className="p-1.5 rounded hover:bg-muted text-sm"
        >
          &larr;
        </button>
        <span className="text-sm font-medium">
          {MONTH_NAMES[viewMonth - 1]} {viewYear}
        </span>
        <button
          type="button"
          onClick={() => navigateMonth(1)}
          className="p-1.5 rounded hover:bg-muted text-sm"
        >
          &rarr;
        </button>
      </div>

      {/* Day-of-week headers */}
      <div className="grid grid-cols-7 gap-1">
        {DAY_NAMES.map((d) => (
          <div key={d} className="text-center text-[10px] font-medium text-muted-foreground py-1">
            {d}
          </div>
        ))}

        {/* Calendar cells */}
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

      {/* Month stats + legend */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] text-muted-foreground">
        <div className="flex gap-3">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded bg-emerald-50 border border-emerald-300" />
            Cheap
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded bg-amber-50 border border-amber-300" />
            Average
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded bg-red-50 border border-red-300" />
            Expensive
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-foreground" />
            {" "}Direct
          </span>
          <span className="flex items-center gap-1">
            <span className="text-[9px]">{"\u2715"}</span>
            {" "}Connecting
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded ring-2 ring-blue-500" />
            Preferred
          </span>
        </div>

        <div className="flex gap-4">
          {cheapestPrice < Infinity && (
            <span>
              Cheapest: <span className="font-medium text-emerald-600">${Math.round(cheapestPrice)}</span>
            </span>
          )}
          {avgPrice > 0 && (
            <span>Avg: ${avgPrice}</span>
          )}
          <span>{directCount} days with direct flights</span>
        </div>
      </div>
    </div>
  );
}
