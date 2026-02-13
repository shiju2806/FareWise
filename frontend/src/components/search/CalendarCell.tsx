import { useState, useRef } from "react";
import type { PriceCalendarDate } from "@/types/search";
import type { DateEvent } from "@/types/event";
import { EventBadge } from "@/components/events/EventBadge";
import { EventTooltip } from "@/components/events/EventTooltip";

interface Props {
  date: string;
  data: PriceCalendarDate;
  isPreferred: boolean;
  isCheapest: boolean;
  isSelected: boolean;
  allMinPrices: number[];
  events?: DateEvent[];
  onClick: (date: string) => void;
}

export function CalendarCell({
  date,
  data,
  isPreferred,
  isCheapest,
  isSelected,
  allMinPrices,
  events = [],
  onClick,
}: Props) {
  const [showTooltip, setShowTooltip] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>();

  const dayName = new Date(date + "T12:00:00").toLocaleDateString("en-US", {
    weekday: "short",
  });
  const dayNum = new Date(date + "T12:00:00").getDate();
  const monthShort = new Date(date + "T12:00:00").toLocaleDateString("en-US", {
    month: "short",
  });

  // Color based on quartile
  const sortedPrices = [...allMinPrices].sort((a, b) => a - b);
  const q1 = sortedPrices[Math.floor(sortedPrices.length * 0.25)] ?? data.min_price;
  const q2 = sortedPrices[Math.floor(sortedPrices.length * 0.5)] ?? data.min_price;
  const q3 = sortedPrices[Math.floor(sortedPrices.length * 0.75)] ?? data.min_price;

  let colorClass = "bg-red-50 text-red-700 border-red-200";
  if (data.min_price <= q1) {
    colorClass = "bg-emerald-50 text-emerald-700 border-emerald-200";
  } else if (data.min_price <= q2) {
    colorClass = "bg-emerald-50/50 text-emerald-600 border-emerald-100";
  } else if (data.min_price <= q3) {
    colorClass = "bg-amber-50 text-amber-700 border-amber-200";
  }

  const hasEvents = events.length > 0;

  function handleMouseEnter() {
    if (hasEvents) {
      timeoutRef.current = setTimeout(() => setShowTooltip(true), 300);
    }
  }

  function handleMouseLeave() {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setShowTooltip(false);
  }

  return (
    <div
      className="relative"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <button
        type="button"
        onClick={() => onClick(date)}
        className={`
          flex flex-col items-center justify-center p-2 rounded-lg border text-center
          transition-all hover:shadow-md cursor-pointer min-w-[72px]
          ${colorClass}
          ${isPreferred ? "ring-2 ring-blue-500 ring-offset-1" : ""}
          ${isSelected ? "ring-2 ring-primary ring-offset-1" : ""}
          ${isCheapest ? "border-2 border-emerald-500" : ""}
        `}
      >
        <span className="text-[10px] font-medium opacity-70">
          {dayName}
        </span>
        <span className="text-xs opacity-70">
          {monthShort} {dayNum}
        </span>
        <span className="text-sm font-bold mt-0.5">
          ${Math.round(data.min_price)}
        </span>
        <span className="text-[10px] opacity-60">
          {data.option_count} opts
        </span>
        {hasEvents && (
          <div className="mt-0.5">
            <EventBadge events={events} compact />
          </div>
        )}
      </button>

      {/* Tooltip */}
      {showTooltip && hasEvents && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50">
          <EventTooltip events={events} date={date} />
        </div>
      )}
    </div>
  );
}
