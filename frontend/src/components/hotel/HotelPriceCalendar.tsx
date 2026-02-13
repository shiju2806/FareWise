import type { HotelPriceCalendarEntry } from "@/types/hotel";

interface Props {
  calendar: HotelPriceCalendarEntry[];
  onDateSelect?: (checkIn: string, checkOut: string) => void;
}

export function HotelPriceCalendar({ calendar, onDateSelect }: Props) {
  if (calendar.length === 0) return null;

  const rates = calendar.map((e) => e.nightly_rate);
  const minRate = Math.min(...rates);
  const maxRate = Math.max(...rates);
  const range = maxRate - minRate || 1;

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">Check-in Date Comparison</h3>
      <div className="flex gap-2 overflow-x-auto pb-2">
        {calendar.map((entry) => {
          const ratio = (entry.nightly_rate - minRate) / range;
          let colorClass = "bg-emerald-50 text-emerald-700 border-emerald-200";
          if (ratio > 0.66) {
            colorClass = "bg-red-50 text-red-700 border-red-200";
          } else if (ratio > 0.33) {
            colorClass = "bg-amber-50 text-amber-700 border-amber-200";
          }

          const date = new Date(entry.check_in + "T12:00:00");
          const dayName = date.toLocaleDateString("en-US", { weekday: "short" });
          const dayNum = date.getDate();
          const month = date.toLocaleDateString("en-US", { month: "short" });

          return (
            <button
              key={entry.check_in}
              type="button"
              onClick={() => onDateSelect?.(entry.check_in, entry.check_out)}
              className={`flex flex-col items-center p-2 rounded-lg border min-w-[80px] transition-all hover:shadow-md ${colorClass} ${
                entry.is_preferred ? "ring-2 ring-blue-500 ring-offset-1" : ""
              }`}
            >
              <span className="text-[10px] font-medium opacity-70">{dayName}</span>
              <span className="text-xs opacity-70">{month} {dayNum}</span>
              <span className="text-sm font-bold mt-0.5">
                ${Math.round(entry.nightly_rate)}
              </span>
              <span className="text-[10px] opacity-60">
                ${Math.round(entry.total_rate)} total
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
