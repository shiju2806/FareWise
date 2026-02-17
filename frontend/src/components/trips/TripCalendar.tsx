import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import apiClient from "@/api/client";
import { CalendarNav } from "./CalendarNav";
import { TripBar, getBarColor } from "./TripBar";
import type { CalendarTripData, BarSegment } from "./TripBar";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface CalendarDay {
  date: string; // YYYY-MM-DD
  day: number;
  isCurrentMonth: boolean;
  isToday: boolean;
}

function buildMonthGrid(year: number, month: number): CalendarDay[] {
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  const firstOfMonth = new Date(year, month, 1);
  // Monday = 0, Sunday = 6
  let startDow = firstOfMonth.getDay() - 1;
  if (startDow < 0) startDow = 6;

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysInPrevMonth = new Date(year, month, 0).getDate();

  const days: CalendarDay[] = [];

  // Previous month's trailing days
  for (let i = startDow - 1; i >= 0; i--) {
    const d = daysInPrevMonth - i;
    const m = month === 0 ? 12 : month;
    const y = month === 0 ? year - 1 : year;
    const dateStr = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    days.push({ date: dateStr, day: d, isCurrentMonth: false, isToday: dateStr === todayStr });
  }

  // Current month days
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    days.push({ date: dateStr, day: d, isCurrentMonth: true, isToday: dateStr === todayStr });
  }

  // Next month's leading days to fill the last row
  const remaining = 7 - (days.length % 7);
  if (remaining < 7) {
    for (let d = 1; d <= remaining; d++) {
      const m = month === 11 ? 1 : month + 2;
      const y = month === 11 ? year + 1 : year;
      const dateStr = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      days.push({ date: dateStr, day: d, isCurrentMonth: false, isToday: dateStr === todayStr });
    }
  }

  return days;
}

function getSegment(date: string, startDate: string, endDate: string, dayOfWeek: number): BarSegment {
  const isStart = date === startDate;
  const isEnd = date === endDate;
  const isMonday = dayOfWeek === 0; // Mon in our 0-indexed system
  const isSunday = dayOfWeek === 6;

  if (isStart && isEnd) return "single";
  if (isStart || isMonday) return "start";
  if (isEnd || isSunday) return "end";
  return "middle";
}

export function TripCalendar() {
  const navigate = useNavigate();
  const now = new Date();
  const [viewYear, setViewYear] = useState(now.getFullYear());
  const [viewMonth, setViewMonth] = useState(now.getMonth());
  const [trips, setTrips] = useState<CalendarTripData[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  useEffect(() => {
    const monthStr = `${viewYear}-${String(viewMonth + 1).padStart(2, "0")}`;
    setLoading(true);
    apiClient
      .get(`/trips/calendar?month=${monthStr}`)
      .then((res) => setTrips(res.data.trips))
      .catch(() => setTrips([]))
      .finally(() => setLoading(false));
  }, [viewYear, viewMonth]);

  const days = useMemo(() => buildMonthGrid(viewYear, viewMonth), [viewYear, viewMonth]);

  // Build a map: date -> list of trips active on that date (with stable ordering)
  const tripsByDate = useMemo(() => {
    const map = new Map<string, CalendarTripData[]>();
    for (const trip of trips) {
      // Walk from start_date to end_date
      const start = new Date(trip.start_date + "T00:00:00");
      const end = new Date(trip.end_date + "T00:00:00");
      const cursor = new Date(start);
      while (cursor <= end) {
        const key = cursor.toISOString().slice(0, 10);
        if (!map.has(key)) map.set(key, []);
        map.get(key)!.push(trip);
        cursor.setDate(cursor.getDate() + 1);
      }
    }
    return map;
  }, [trips]);

  // Stable color assignment by trip id
  const tripColorMap = useMemo(() => {
    const map = new Map<string, string>();
    trips.forEach((t, i) => map.set(t.id, getBarColor(i)));
    return map;
  }, [trips]);

  function handleMonthChange(y: number, m: number) {
    setViewYear(y);
    setViewMonth(m);
  }

  return (
    <div>
      <CalendarNav year={viewYear} month={viewMonth} onChange={handleMonthChange} />

      {/* Day headers */}
      <div className="grid grid-cols-7 mb-1">
        {DAY_LABELS.map((label) => (
          <div
            key={label}
            className="text-[10px] font-medium text-muted-foreground text-center py-1"
          >
            {label}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 border-l border-t border-border">
        {days.map((day, idx) => {
          const dayTrips = tripsByDate.get(day.date) || [];
          const dayOfWeek = idx % 7;

          return (
            <div
              key={day.date}
              onClick={() => {
                if (dayTrips.length > 0) {
                  setSelectedDate(selectedDate === day.date ? null : day.date);
                }
              }}
              className={`
                min-h-[80px] border-r border-b border-border p-1
                ${day.isCurrentMonth ? "bg-background" : "bg-muted/30"}
                ${day.isToday ? "ring-1 ring-inset ring-primary/40" : ""}
                ${dayTrips.length > 0 ? "cursor-pointer hover:bg-muted/50" : ""}
                ${selectedDate === day.date ? "ring-2 ring-inset ring-primary" : ""}
              `}
            >
              <span
                className={`
                  text-[11px] leading-none
                  ${day.isCurrentMonth ? "text-foreground" : "text-muted-foreground/50"}
                  ${day.isToday ? "font-bold text-primary" : ""}
                `}
              >
                {day.day}
              </span>

              <div className="mt-0.5 space-y-0.5">
                {dayTrips.slice(0, 3).map((trip) => (
                  <TripBar
                    key={trip.id}
                    trip={trip}
                    segment={getSegment(day.date, trip.start_date, trip.end_date, dayOfWeek)}
                    colorClass={tripColorMap.get(trip.id) || "bg-blue-500"}
                    onClick={() => navigate(`/trips/${trip.id}/search`)}
                  />
                ))}
                {dayTrips.length > 3 && (
                  <span className="text-[9px] text-muted-foreground pl-0.5">
                    +{dayTrips.length - 3} more
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Date detail popover */}
      {selectedDate && tripsByDate.get(selectedDate) && (
        <div className="border border-border rounded-lg p-3 mt-2 space-y-2 bg-card shadow-sm">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium">{selectedDate}</h4>
            <button
              onClick={() => setSelectedDate(null)}
              className="text-muted-foreground hover:text-foreground text-xs"
            >
              &times;
            </button>
          </div>
          {tripsByDate.get(selectedDate)!.map((trip) => (
            <div
              key={trip.id}
              className="flex items-center justify-between text-sm py-1.5 px-2 rounded hover:bg-muted/50 cursor-pointer"
              onClick={() => navigate(`/trips/${trip.id}/search`)}
            >
              <span className="truncate mr-3">
                {trip.title || trip.legs.map((l) => `${l.origin}\u2192${l.destination}`).join(", ")}
              </span>
              <span
                className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 ${
                  trip.status === "approved"
                    ? "bg-green-100 text-green-700"
                    : trip.status === "submitted"
                    ? "bg-blue-100 text-blue-700"
                    : trip.status === "changes_requested"
                    ? "bg-amber-100 text-amber-700"
                    : trip.status === "rejected"
                    ? "bg-red-100 text-red-700"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {trip.status.replace("_", " ")}
              </span>
            </div>
          ))}
        </div>
      )}

      {loading && (
        <div className="text-center py-4 text-xs text-muted-foreground">
          Loading trips...
        </div>
      )}

      {!loading && trips.length === 0 && (
        <div className="text-center py-8 text-sm text-muted-foreground">
          No trips this month
        </div>
      )}
    </div>
  );
}
