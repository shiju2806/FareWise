import { useState } from "react";
import type { SearchResult } from "@/types/search";
import type { FlightOption } from "@/types/flight";
import { PriceCalendar } from "./PriceCalendar";
import { FlightOptionCard } from "./FlightOptionCard";
import { WhatIfSlider } from "./WhatIfSlider";
import { RouteComparator } from "./RouteComparator";

interface Props {
  result: SearchResult;
  sliderValue: number;
  sliderLoading: boolean;
  onSliderChange: (value: number) => void;
  onDateSelect: (date: string) => void;
  onFlightSelect?: (flight: FlightOption) => void;
}

export function SearchResults({
  result,
  sliderValue,
  sliderLoading,
  onSliderChange,
  onDateSelect,
  onFlightSelect,
}: Props) {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

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
        <span>Search time: {result.metadata.search_time_ms}ms</span>
      </div>

      {/* Price Calendar */}
      <PriceCalendar
        calendar={result.price_calendar}
        preferredDate={result.leg.preferred_date}
        selectedDate={selectedDate}
        onDateSelect={handleDateSelect}
      />

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
