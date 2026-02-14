import { useState } from "react";
import type { SearchResult } from "@/types/search";
import type { FlightOption } from "@/types/flight";
import type { DateEvent, EventData } from "@/types/event";
import { MonthCalendar } from "./MonthCalendar";
import { PriceAdvisorPanel } from "./PriceAdvisorPanel";
import { FlightOptionCard } from "./FlightOptionCard";
import { WhatIfSlider } from "./WhatIfSlider";
import { RouteComparator } from "./RouteComparator";
import { WhyThisPrice } from "@/components/events/WhyThisPrice";
import { EventPanel } from "@/components/events/EventPanel";
import { PriceWatchSetup } from "@/components/pricewatch/PriceWatchSetup";

interface Props {
  result: SearchResult;
  legId: string;
  sliderValue: number;
  sliderLoading: boolean;
  onSliderChange: (value: number) => void;
  onDateSelect: (date: string) => void;
  onFlightSelect?: (flight: FlightOption) => void;
  dateEvents?: Record<string, DateEvent[]>;
  allEvents?: EventData[];
  eventSummary?: { recommendation: string | null } | null;
  destination?: string;
}

export function SearchResults({
  result,
  legId,
  sliderValue,
  sliderLoading,
  onSliderChange,
  onDateSelect,
  onFlightSelect,
  dateEvents = {},
  allEvents = [],
  eventSummary,
  destination,
}: Props) {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [whyPriceDate, setWhyPriceDate] = useState<string | null>(null);
  const [showEventPanel, setShowEventPanel] = useState(false);
  const [showWatchForm, setShowWatchForm] = useState(false);

  function handleDateSelect(date: string) {
    setSelectedDate(date);
    onDateSelect(date);
  }

  const displayOptions = showAll
    ? result.all_options
    : result.all_options.slice(0, 5);

  // Empty state
  if (result.all_options.length === 0) {
    return (
      <div className="text-center py-12 space-y-3">
        <p className="text-lg font-medium">No flights found</p>
        <p className="text-sm text-muted-foreground">
          No flight options were found for this route and date range. Try
          adjusting your dates or enabling nearby airports.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Search metadata */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {result.metadata.total_options_found} options found across{" "}
          {result.metadata.airports_searched.length} airports and{" "}
          {result.metadata.dates_searched.length} dates
        </span>
        <div className="flex items-center gap-3">
          <span>Search time: {result.metadata.search_time_ms}ms</span>
          <button
            type="button"
            onClick={() => setShowWatchForm(!showWatchForm)}
            className="text-primary hover:underline font-medium"
          >
            {showWatchForm ? "Cancel" : "Watch Price"}
          </button>
        </div>
      </div>

      {showWatchForm && (
        <PriceWatchSetup
          defaultOrigin={result.leg.origin}
          defaultDestination={result.leg.destination}
          defaultDate={result.leg.preferred_date}
          defaultPrice={result.recommendation?.price}
          onCreated={() => setShowWatchForm(false)}
        />
      )}

      {/* Event recommendation banner */}
      {eventSummary?.recommendation && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 flex items-start gap-2">
          <span className="text-base mt-0.5">{"\u26A0\uFE0F"}</span>
          <div className="flex-1">
            <p>{eventSummary.recommendation}</p>
            <button
              type="button"
              onClick={() => setShowEventPanel(true)}
              className="text-xs text-amber-700 hover:underline mt-1"
            >
              View all events
            </button>
          </div>
        </div>
      )}

      {/* Month Price Calendar */}
      <MonthCalendar
        legId={legId}
        preferredDate={result.leg.preferred_date}
        initialCalendar={result.price_calendar}
        selectedDate={selectedDate}
        onDateSelect={handleDateSelect}
      />

      {/* Price Intelligence Advisor */}
      <PriceAdvisorPanel legId={legId} />

      {/* Why This Price? panel */}
      {whyPriceDate && (
        <WhyThisPrice
          date={whyPriceDate}
          events={dateEvents[whyPriceDate] || []}
          price={
            result.price_calendar.dates[whyPriceDate]?.min_price ?? 0
          }
          onClose={() => setWhyPriceDate(null)}
        />
      )}

      {/* Event panel */}
      {showEventPanel && (
        <EventPanel
          events={allEvents}
          destination={destination || result.leg.destination}
          onClose={() => setShowEventPanel(false)}
        />
      )}

      {/* What If Slider */}
      <WhatIfSlider
        value={sliderValue}
        onChange={onSliderChange}
        loading={sliderLoading}
      />

      {/* Recommendation */}
      {result.recommendation && (
        <div>
          <h3 className="text-sm font-semibold mb-2">Recommended</h3>
          <FlightOptionCard
            flight={result.recommendation}
            isRecommended
            reason={result.recommendation.reason}
            onSelect={onFlightSelect}
          />
        </div>
      )}

      {/* Alternatives */}
      <RouteComparator
        alternatives={result.alternatives}
        onSelect={onFlightSelect}
      />

      {/* All Options */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">
            All Options ({result.all_options.length})
          </h3>
        </div>

        <div className="space-y-2">
          {displayOptions.map((flight, i) => (
            <FlightOptionCard
              key={flight.id || i}
              flight={flight}
              onSelect={onFlightSelect}
            />
          ))}
        </div>

        {result.all_options.length > 5 && (
          <button
            type="button"
            onClick={() => setShowAll(!showAll)}
            className="text-sm text-primary hover:underline"
          >
            {showAll
              ? "Show less"
              : `Show all ${result.all_options.length} options`}
          </button>
        )}
      </div>
    </div>
  );
}
