import type { PriceCalendar as PriceCalendarType } from "@/types/search";
import type { DateEvent } from "@/types/event";
import { CalendarCell } from "./CalendarCell";

interface Props {
  calendar: PriceCalendarType;
  preferredDate: string;
  selectedDate: string | null;
  dateEvents?: Record<string, DateEvent[]>;
  onDateSelect: (date: string) => void;
  onWhyThisPrice?: (date: string) => void;
}

export function PriceCalendar({
  calendar,
  preferredDate,
  selectedDate,
  dateEvents = {},
  onDateSelect,
  onWhyThisPrice,
}: Props) {
  const sortedDates = Object.keys(calendar.dates).sort();
  const allMinPrices = sortedDates.map((d) => calendar.dates[d].min_price);

  const hasAnyEvents = Object.values(dateEvents).some((evts) => evts.length > 0);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Price Calendar</h3>
        {calendar.savings_if_flexible > 0 && (
          <span className="text-xs text-emerald-600 font-medium">
            Save ${Math.round(calendar.savings_if_flexible)} with flexible dates
          </span>
        )}
      </div>

      <div className="flex gap-2 overflow-x-auto pb-2">
        {sortedDates.map((date) => (
          <CalendarCell
            key={date}
            date={date}
            data={calendar.dates[date]}
            isPreferred={date === preferredDate}
            isCheapest={date === calendar.cheapest_date}
            isSelected={date === selectedDate}
            allMinPrices={allMinPrices}
            events={dateEvents[date]}
            onClick={onDateSelect}
          />
        ))}
      </div>

      <div className="flex gap-4 text-[10px] text-muted-foreground flex-wrap">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-emerald-100 border border-emerald-300" />
          Cheapest
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-amber-100 border border-amber-300" />
          Average
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-red-100 border border-red-300" />
          Expensive
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded border-2 border-blue-500" />
          Preferred
        </span>
        {hasAnyEvents && (
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded bg-orange-100 border border-orange-300 text-center text-[7px] leading-3">
              !
            </span>
            Event
          </span>
        )}
      </div>

      {/* "Why This Price?" link */}
      {selectedDate && onWhyThisPrice && (
        <button
          type="button"
          onClick={() => onWhyThisPrice(selectedDate)}
          className="text-xs text-primary hover:underline"
        >
          Why this price?
        </button>
      )}
    </div>
  );
}
