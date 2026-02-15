import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { TripCalendar } from "@/components/trips/TripCalendar";
import TripHistory from "./TripHistory";

type ViewMode = "calendar" | "list";

export default function Trips() {
  const [view, setView] = useState<ViewMode>(
    () => (localStorage.getItem("trips-view") as ViewMode) || "calendar"
  );

  function setViewMode(mode: ViewMode) {
    setView(mode);
    localStorage.setItem("trips-view", mode);
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold tracking-tight">Trips</h2>
        <div className="flex items-center gap-3">
          {/* View toggle */}
          <div className="flex rounded-md border border-border overflow-hidden">
            <button
              type="button"
              onClick={() => setViewMode("calendar")}
              className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
                view === "calendar"
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:bg-accent"
              }`}
              aria-label="Calendar view"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                />
              </svg>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("list")}
              className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
                view === "list"
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:bg-accent"
              }`}
              aria-label="List view"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              </svg>
            </button>
          </div>

          <Link to="/trips/new">
            <Button size="sm">New Trip</Button>
          </Link>
        </div>
      </div>

      {/* View content */}
      {view === "calendar" ? <TripCalendar /> : <TripHistory />}
    </div>
  );
}
