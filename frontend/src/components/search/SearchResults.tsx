import { useState, useMemo, useCallback, useEffect } from "react";
import type { SearchResult } from "@/types/search";
import type { FlightOption } from "@/types/flight";
import type { DateEvent, EventData } from "@/types/event";
import { MonthCalendar } from "./MonthCalendar";
import { PriceAdvisorPanel } from "./PriceAdvisorPanel";
import { FlightOptionCard } from "./FlightOptionCard";
import { WhatIfSlider } from "./WhatIfSlider";
import { AirlineDateMatrix } from "./AirlineDateMatrix";
import { WhyThisPrice } from "@/components/events/WhyThisPrice";
import { EventPanel } from "@/components/events/EventPanel";
import { PriceWatchSetup } from "@/components/pricewatch/PriceWatchSetup";
import { usePriceIntelStore } from "@/stores/priceIntelStore";

interface Props {
  result: SearchResult;
  legId: string;
  sliderValue: number;
  sliderLoading: boolean;
  onSliderChange: (value: number) => void;
  onDateSelect: (date: string) => void;
  onFlightSelect?: (flight: FlightOption) => void;
  selectedFlightId?: string;
  excludedAirlines?: string[];
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
  selectedFlightId,
  excludedAirlines = [],
  dateEvents = {},
  allEvents = [],
  eventSummary,
  destination,
}: Props) {
  const [selectedDate, setSelectedDate] = useState<string | null>(
    result.leg.preferred_date
  );

  // Reset date filter when switching legs
  useEffect(() => {
    setSelectedDate(result.leg.preferred_date);
  }, [result.leg.preferred_date]);
  const [showAll, setShowAll] = useState(false);
  const [whyPriceDate, setWhyPriceDate] = useState<string | null>(null);
  const [showEventPanel, setShowEventPanel] = useState(false);
  const [showWatchForm, setShowWatchForm] = useState(false);
  const [airlineFilter, setAirlineFilter] = useState<Set<string>>(new Set());
  const [maxBudget, setMaxBudget] = useState<number | null>(null);

  // Matrix data from DB1B calendar (keyed by "legId:YYYY-MM")
  const prefDate = new Date(result.leg.preferred_date + "T00:00:00");
  const [matrixYear, setMatrixYear] = useState(prefDate.getFullYear());
  const [matrixMonth, setMatrixMonth] = useState(prefDate.getMonth() + 1);
  const { matrixData, fetchMonthMatrix } = usePriceIntelStore();
  const matrixKey = `${legId}:${matrixYear}-${String(matrixMonth).padStart(2, "0")}`;
  const externalMatrixData = matrixData[matrixKey] ?? undefined;

  // Fetch matrix data on initial mount
  useEffect(() => {
    fetchMonthMatrix(legId, matrixYear, matrixMonth);
  }, [legId, matrixYear, matrixMonth, fetchMonthMatrix]);

  const handleMonthChange = useCallback(
    (year: number, month: number) => {
      setMatrixYear(year);
      setMatrixMonth(month);
    },
    []
  );

  function handleDateSelect(date: string) {
    // If clicking the already-selected date, deselect (unless it's the preferred date — keep it)
    const newDate = date === selectedDate && date !== result.leg.preferred_date ? null : date;
    setSelectedDate(newDate);
    onDateSelect(date);
  }

  // Cheapest flight per airline (for filter chips)
  const cheapestByAirline = useMemo(() => {
    const map = new Map<string, FlightOption>();
    for (const f of result.all_options) {
      const name = f.airline_name;
      if (!map.has(name) || f.price < map.get(name)!.price) {
        map.set(name, f);
      }
    }
    return Array.from(map.values()).sort((a, b) => a.price - b.price);
  }, [result.all_options]);

  // Identify the recommended flight ID for highlighting in the list
  const recommendedId = result.recommendation?.id;

  function toggleAirline(name: string) {
    setAirlineFilter((prev) => {
      // Single-select: clicking same airline deselects, clicking different switches
      if (prev.has(name)) {
        return new Set();
      }
      return new Set([name]);
    });
  }

  // Filter by selected date
  const dateHasFlights = useMemo(
    () =>
      selectedDate
        ? result.all_options.some((f) => f.departure_time.startsWith(selectedDate))
        : false,
    [selectedDate, result.all_options]
  );

  const filteredOptions = useMemo(() => {
    let opts = selectedDate && dateHasFlights
      ? result.all_options.filter((f) => f.departure_time.startsWith(selectedDate))
      : result.all_options;

    if (airlineFilter.size > 0) {
      opts = opts.filter((f) => airlineFilter.has(f.airline_name));
    }

    if (maxBudget != null) {
      opts = opts.filter((f) => f.price <= maxBudget);
    }

    return opts;
  }, [result.all_options, selectedDate, dateHasFlights, airlineFilter, maxBudget]);

  const preBudgetCount = useMemo(() => {
    let opts = selectedDate && dateHasFlights
      ? result.all_options.filter((f) => f.departure_time.startsWith(selectedDate))
      : result.all_options;
    if (airlineFilter.size > 0) {
      opts = opts.filter((f) => airlineFilter.has(f.airline_name));
    }
    return opts.length;
  }, [result.all_options, selectedDate, dateHasFlights, airlineFilter]);

  const displayOptions = useMemo(
    () => (showAll ? filteredOptions : filteredOptions.slice(0, 15)),
    [showAll, filteredOptions]
  );

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

  // Price quartiles for color-coding throughout
  const priceQuartiles = useMemo(() => {
    const prices = result.all_options.map((f) => f.price).sort((a, b) => a - b);
    if (prices.length === 0) return { q1: 0, q3: 0 };
    return {
      q1: prices[Math.floor(prices.length * 0.25)],
      q3: prices[Math.floor(prices.length * 0.75)],
    };
  }, [result.all_options]);

  return (
    <div className="space-y-4">
      {/* 1. Search metadata bar */}
      <div className="flex items-center justify-between text-xs text-muted-foreground bg-muted/40 rounded-lg px-3 py-2 shadow-sm">
        <span>
          {result.metadata.total_options_found} options across{" "}
          {result.metadata.airports_searched.length} airports,{" "}
          {result.metadata.dates_searched.length} dates
          <span className="mx-1.5 opacity-40">|</span>
          {result.metadata.search_time_ms}ms
        </span>
        <button
          type="button"
          onClick={() => setShowWatchForm(!showWatchForm)}
          className="text-primary hover:underline font-medium"
        >
          {showWatchForm ? "Cancel" : "Watch Price"}
        </button>
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

      {/* 2. Event warning banner */}
      {eventSummary?.recommendation && (
        <div className="rounded-md border border-amber-200 bg-amber-50/80 px-3 py-2 text-sm text-amber-800 flex items-center gap-2">
          <span className="shrink-0 w-5 h-5 rounded-full bg-amber-200 flex items-center justify-center text-[10px] font-bold">!</span>
          <p className="flex-1 text-xs">{eventSummary.recommendation}</p>
          <button
            type="button"
            onClick={() => setShowEventPanel(true)}
            className="text-[10px] text-amber-700 hover:underline shrink-0"
          >
            View events
          </button>
        </div>
      )}

      {/* 3. Month Price Calendar */}
      <div className="rounded-lg bg-muted/20 p-3 shadow-sm">
        <MonthCalendar
          legId={legId}
          preferredDate={result.leg.preferred_date}
          initialCalendar={result.price_calendar}
          selectedDate={selectedDate}
          onDateSelect={handleDateSelect}
          onMonthChange={handleMonthChange}
          activeAirline={airlineFilter.size === 1 ? Array.from(airlineFilter)[0] : null}
          allOptions={result.all_options}
        />
      </div>

      {/* 4. Airline x Date Price Matrix (grouped with calendar for exploration) */}
      <div className="rounded-lg bg-muted/15 p-3 shadow-sm">
        <AirlineDateMatrix
          allOptions={result.all_options}
          datesSearched={result.metadata.dates_searched}
          excludedAirlines={excludedAirlines}
          onFlightSelect={onFlightSelect}
          onAirlineToggle={toggleAirline}
          activeAirlines={airlineFilter}
          selectedDate={selectedDate}
          preferredDate={result.leg.preferred_date}
          externalMatrixData={externalMatrixData}
          maxBudget={maxBudget}
        />
      </div>

      {/* 5. Airline filter chips + budget filter + date filter */}
      <div className="flex items-center gap-2 flex-wrap">
        {cheapestByAirline.length > 1 &&
          cheapestByAirline.map((f) => (
            <button
              key={f.airline_name}
              type="button"
              onClick={() => toggleAirline(f.airline_name)}
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium transition-all ${
                airlineFilter.has(f.airline_name)
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
              }`}
            >
              {f.airline_name}
              <span className="text-[10px] opacity-60">${Math.round(f.price)}</span>
            </button>
          ))}
        {airlineFilter.size > 0 && (
          <button
            type="button"
            onClick={() => setAirlineFilter(new Set())}
            className="text-[11px] text-primary hover:underline px-1"
          >
            Clear
          </button>
        )}

        <span className="text-muted-foreground text-[10px]">|</span>

        {/* Budget filter */}
        <div className="inline-flex items-center gap-1">
          <span className="text-[11px] text-muted-foreground">$</span>
          <input
            type="number"
            placeholder="Max budget"
            value={maxBudget ?? ""}
            onChange={(e) => {
              const v = e.target.value;
              setMaxBudget(v === "" ? null : Number(v));
            }}
            className="w-20 rounded border border-border bg-background px-1.5 py-0.5 text-[11px] focus:outline-none focus:ring-1 focus:ring-primary"
          />
          {maxBudget != null && (
            <>
              <button
                type="button"
                onClick={() => setMaxBudget(null)}
                className="text-[11px] text-primary hover:underline"
              >
                Clear
              </button>
              <span className="text-[10px] text-muted-foreground">
                {filteredOptions.length} of {preBudgetCount} under ${maxBudget.toLocaleString()}
              </span>
            </>
          )}
        </div>

        {selectedDate && (
          <>
            <span className="text-muted-foreground text-[10px]">|</span>
            <span className="text-[11px] font-medium">
              {dateHasFlights ? (
                <>{selectedDate} ({filteredOptions.length})</>
              ) : (
                <>{selectedDate} <span className="text-muted-foreground">(calendar only)</span></>
              )}
            </span>
            <button
              type="button"
              onClick={() => setSelectedDate(null)}
              className="text-[11px] text-primary hover:underline"
            >
              Clear date
            </button>
          </>
        )}
      </div>

      {/* 6. Price Intelligence Advisor */}
      <PriceAdvisorPanel legId={legId} />

      {/* Hidden panels (triggered by calendar/events) */}
      {whyPriceDate && (
        <WhyThisPrice
          date={whyPriceDate}
          events={dateEvents[whyPriceDate] || []}
          price={result.price_calendar.dates[whyPriceDate]?.min_price ?? 0}
          onClose={() => setWhyPriceDate(null)}
        />
      )}
      {showEventPanel && (
        <EventPanel
          events={allEvents}
          destination={destination || result.leg.destination}
          onClose={() => setShowEventPanel(false)}
        />
      )}

      {/* 7. What If Slider */}
      <WhatIfSlider
        value={sliderValue}
        onChange={onSliderChange}
        loading={sliderLoading}
      />

      {/* 8. Flight list (compact rows, recommendation integrated) */}
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            {selectedDate
              ? `Flights on ${selectedDate}`
              : `All Flights (${filteredOptions.length})`}
          </h3>
          {selectedDate && (
            <button
              type="button"
              onClick={() => setSelectedDate(null)}
              className="text-[10px] text-primary hover:underline"
            >
              Show all dates
            </button>
          )}
        </div>

        {filteredOptions.length === 0 && selectedDate && dateHasFlights && (
          <p className="text-sm text-muted-foreground py-4 text-center">
            No flights match filters.{" "}
            <button
              type="button"
              onClick={() => { setSelectedDate(null); setAirlineFilter(new Set()); }}
              className="text-primary hover:underline"
            >
              Clear all filters
            </button>
          </p>
        )}

        <div className="space-y-1">
          {displayOptions.map((flight, i) => (
            <FlightOptionCard
              key={flight.id || i}
              flight={flight}
              isRecommended={flight.id === recommendedId}
              isSelected={flight.id === selectedFlightId}
              reason={flight.id === recommendedId ? result.recommendation?.reason : undefined}
              onSelect={onFlightSelect}
              priceQuartiles={priceQuartiles}
              preferredDate={result.leg.preferred_date}
              showDate={!selectedDate}
            />
          ))}
        </div>

        {filteredOptions.length > 15 && (
          <button
            type="button"
            onClick={() => setShowAll(!showAll)}
            className="text-xs text-primary hover:underline w-full text-center py-2"
          >
            {showAll
              ? "Show less"
              : `Show all ${filteredOptions.length} options`}
          </button>
        )}
      </div>
    </div>
  );
}
