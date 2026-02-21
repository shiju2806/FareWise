import { useCallback, useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useTripStore } from "@/stores/tripStore";
import { useSearchStore } from "@/stores/searchStore";
import { useEventStore } from "@/stores/eventStore";
import { SearchResults } from "@/components/search/SearchResults";
import { JustificationModal } from "@/components/search/JustificationModal";
import { TripCostBar } from "@/components/search/TripCostBar";
import { MonthPriceTrend } from "@/components/search/MonthPriceTrend";
import { HotelSearch } from "@/components/hotel/HotelSearch";
import { BundleOptimizer } from "@/components/bundle/BundleOptimizer";
import { LegCard } from "@/components/trip/LegCard";
import { formatPrice } from "@/lib/currency";
import { SearchAssistant } from "@/components/search/SearchAssistant";
import type { FlightOption } from "@/types/flight";
import type { TripWindowProposal } from "@/types/search";
import apiClient from "@/api/client";

/** Normalize any datetime string to YYYY-MM-DD */
function toDateStr(dt: string): string {
  return dt.split("T")[0];
}

export default function TripSearch() {
  const { tripId } = useParams<{ tripId: string }>();
  const navigate = useNavigate();
  const { currentTrip, loading: tripLoading, fetchTrip, patchLeg } = useTripStore();
  const {
    results,
    loading: searchLoading,
    sliderLoading,
    sliderValue,
    error,
    searchStartedAt,
    searchLeg,
    cancelSearch,
    rescoreWithSlider,
    prefetchLeg,
    prefetching,
    clearResults,
  } = useSearchStore();
  const { legEvents, fetchLegEvents } = useEventStore();

  const [activeLegIndex, setActiveLegIndex] = useState(0);
  // Per-leg flight selections (keyed by legId)
  const [selectedFlights, setSelectedFlights] = useState<Record<string, FlightOption>>({});
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [showReturnForm, setShowReturnForm] = useState(false);
  const [returnDate, setReturnDate] = useState("");
  const [addingReturn, setAddingReturn] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [justificationAnalysis, setJustificationAnalysis] = useState<any>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [hasSwitched, setHasSwitched] = useState(false);
  const [excludedAirlines, setExcludedAirlines] = useState<string[]>([]);
  const [elapsed, setElapsed] = useState(0);

  // Elapsed timer for search
  useEffect(() => {
    if (!searchLoading || !searchStartedAt) {
      setElapsed(0);
      return;
    }
    setElapsed(Math.floor((Date.now() - searchStartedAt) / 1000));
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - searchStartedAt) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [searchLoading, searchStartedAt]);

  useEffect(() => {
    if (tripId) {
      fetchTrip(tripId);
    }
  }, [tripId, fetchTrip]);

  // Fetch user travel preferences (excluded airlines)
  useEffect(() => {
    apiClient
      .get("/users/me/preferences")
      .then((res) => {
        if (res.data?.excluded_airlines) {
          setExcludedAirlines(res.data.excluded_airlines);
        }
      })
      .catch(() => {});
  }, []);

  const activeLeg = currentTrip?.legs[activeLegIndex];
  const searchResult = activeLeg ? results[activeLeg.id] : null;
  const legEventData = activeLeg ? legEvents[activeLeg.id] : null;

  // The currently selected flight for the active leg
  const activeSelectedFlight = activeLeg ? selectedFlights[activeLeg.id] || null : null;

  // Count how many legs have selections
  const selectedCount = Object.keys(selectedFlights).length;
  const totalLegs = currentTrip?.legs.length || 0;
  const allLegsSelected = selectedCount === totalLegs && totalLegs > 0;

  // Auto-search all legs on initial load (skips legs with cached results)
  const [autoSearched, setAutoSearched] = useState(false);
  useEffect(() => {
    if (currentTrip && !autoSearched) {
      setAutoSearched(true);
      const unsearched = currentTrip.legs.filter((leg) => !results[leg.id]);
      if (unsearched.length > 0) {
        // Search first leg normally (with loading indicator)
        searchLeg(unsearched[0].id);
        // Prefetch remaining legs in background (no loading indicator)
        for (let i = 1; i < unsearched.length; i++) {
          prefetchLeg(unsearched[i].id);
        }
      }
    }
  }, [currentTrip, autoSearched, results, searchLeg, prefetchLeg]);

  // Prefetch remaining unsearched legs when a search completes
  useEffect(() => {
    if (!currentTrip || searchLoading) return;
    const hasAnyResults = currentTrip.legs.some((leg) => results[leg.id]);
    if (!hasAnyResults) return;
    const unsearchedLegs = currentTrip.legs.filter(
      (leg) => !results[leg.id] && !prefetching[leg.id]
    );
    if (unsearchedLegs.length > 0) {
      prefetchLeg(unsearchedLegs[0].id);
    }
  }, [currentTrip, searchLoading, results, prefetching, prefetchLeg]);

  // Auto-search when user manually switches to a leg that hasn't been searched
  const [userSwitchedLeg, setUserSwitchedLeg] = useState(false);
  useEffect(() => {
    if (userSwitchedLeg && activeLeg && !results[activeLeg.id] && !searchLoading) {
      setUserSwitchedLeg(false);
      // If this leg is being prefetched, don't fire a duplicate search
      if (prefetching[activeLeg.id]) return;
      searchLeg(activeLeg.id);
    }
  }, [userSwitchedLeg, activeLeg, results, searchLoading, searchLeg, prefetching]);

  // Fetch events when search results appear
  useEffect(() => {
    if (searchResult && activeLeg) {
      fetchLegEvents(activeLeg.id);
    }
  }, [searchResult, activeLeg, fetchLegEvents]);

  function handleSearch() {
    if (activeLeg) {
      searchLeg(activeLeg.id);
    }
  }

  const handleSliderChange = useCallback(
    (value: number) => {
      if (activeLeg) {
        rescoreWithSlider(activeLeg.id, value);
      }
    },
    [activeLeg, rescoreWithSlider]
  );

  function handleFlightSelect(flight: FlightOption) {
    if (!activeLeg) return;
    setSelectedFlights((prev) => ({ ...prev, [activeLeg.id]: flight }));
  }

  function handleClearSelection() {
    if (!activeLeg) return;
    setSelectedFlights((prev) => {
      const next = { ...prev };
      delete next[activeLeg.id];
      return next;
    });
    setJustificationAnalysis(null);
  }

  function handleTripUpdated() {
    if (tripId) fetchTrip(tripId);
  }

  // Handle switching to a trip-window proposal (shared by inline + modal)
  const handleSwitchTripWindow = useCallback((proposal: TripWindowProposal) => {
    if (!currentTrip || currentTrip.legs.length < 2) return;
    const outLeg = currentTrip.legs[0];
    const retLeg = currentTrip.legs[currentTrip.legs.length - 1];
    const outOptions = results[outLeg.id]?.all_options || [];
    const retOptions = results[retLeg.id]?.all_options || [];

    // Exact match: same airline + same date
    let outFlight = outOptions.find((f) =>
      toDateStr(f.departure_time) === proposal.outbound_date &&
      f.airline_code === proposal.outbound_flight.airline_code
    );
    let retFlight = retOptions.find((f) =>
      toDateStr(f.departure_time) === proposal.return_date &&
      f.airline_code === proposal.return_flight.airline_code
    );

    // Fallback: cheapest flight on that date (any airline)
    if (!outFlight) {
      outFlight = outOptions
        .filter((f) => toDateStr(f.departure_time) === proposal.outbound_date)
        .sort((a, b) => a.price - b.price)[0];
    }
    if (!retFlight) {
      retFlight = retOptions
        .filter((f) => toDateStr(f.departure_time) === proposal.return_date)
        .sort((a, b) => a.price - b.price)[0];
    }

    // If flights not in search results, build from proposal data (DB1B historical)
    if (!outFlight) {
      const pf = proposal.outbound_flight;
      outFlight = {
        id: `db1b-out-${proposal.outbound_date}-${pf.airline_code}`,
        airline_code: pf.airline_code,
        airline_name: pf.airline_name,
        flight_numbers: `${pf.airline_code}`,
        origin_airport: outLeg.origin_airport,
        destination_airport: outLeg.destination_airport,
        departure_time: pf.departure_time || `${proposal.outbound_date}T08:00:00`,
        arrival_time: pf.arrival_time || `${proposal.outbound_date}T17:00:00`,
        duration_minutes: pf.duration_minutes || 0,
        stops: pf.stops,
        stop_airports: null,
        price: pf.price,
        currency: "USD",
        cabin_class: outLeg.cabin_class || null,
        seats_remaining: null,
        is_alternate_airport: false,
        is_alternate_date: true,
        source: "db1b_historical",
      } as FlightOption;
    }
    if (!retFlight) {
      const pf = proposal.return_flight;
      retFlight = {
        id: `db1b-ret-${proposal.return_date}-${pf.airline_code}`,
        airline_code: pf.airline_code,
        airline_name: pf.airline_name,
        flight_numbers: `${pf.airline_code}`,
        origin_airport: retLeg.origin_airport,
        destination_airport: retLeg.destination_airport,
        departure_time: pf.departure_time || `${proposal.return_date}T08:00:00`,
        arrival_time: pf.arrival_time || `${proposal.return_date}T17:00:00`,
        duration_minutes: pf.duration_minutes || 0,
        stops: pf.stops,
        stop_airports: null,
        price: pf.price,
        currency: "USD",
        cabin_class: retLeg.cabin_class || null,
        seats_remaining: null,
        is_alternate_airport: false,
        is_alternate_date: true,
        source: "db1b_historical",
      } as FlightOption;
    }

    setSelectedFlights({ [outLeg.id]: outFlight, [retLeg.id]: retFlight });
    setHasSwitched(true);
  }, [currentTrip, results]);

  // Handle cabin class downgrade (e.g. business → premium economy)
  const handleCabinDowngrade = useCallback(async (suggestedCabin: string) => {
    if (!currentTrip) return;
    try {
      // Patch cabin class on all legs sequentially (avoid store race condition)
      for (const leg of currentTrip.legs) {
        await patchLeg(leg.id, { cabin_class: suggestedCabin });
      }
      // Clear state and re-search
      setJustificationAnalysis(null);
      setHasSwitched(false);
      setSelectedFlights({});
      clearResults();
      setAutoSearched(false);
    } catch (err) {
      console.error("Cabin downgrade failed:", err);
    }
  }, [currentTrip, patchLeg, clearResults]);

  // Confirm all leg selections (trip-level)
  async function handleConfirmTrip() {
    if (!currentTrip || !allLegsSelected || !tripId) return;

    setAnalyzing(true);
    try {
      // Build selected_flights map for trip-level endpoint
      const selectedMap: Record<string, string> = {};
      for (const leg of currentTrip.legs) {
        const flight = selectedFlights[leg.id];
        if (flight) selectedMap[leg.id] = flight.id;
      }

      const res = await apiClient.post(
        `/trips/${tripId}/analyze-selections`,
        { selected_flights: selectedMap }
      );

      if (res.data.justification_required) {
        setJustificationAnalysis(res.data);
        setAnalyzing(false);
        return;
      }
    } catch {
      setAnalyzing(false);
      alert("Could not verify compliance. Please try again.");
      return;
    }
    setAnalyzing(false);

    // No justification needed — confirm all legs
    await confirmAllLegs();
  }

  async function confirmAllLegs(justification?: string) {
    if (!currentTrip || !tripId) return;
    setConfirming(true);
    try {
      for (const leg of currentTrip.legs) {
        const flight = selectedFlights[leg.id];
        if (flight) {
          const payload: Record<string, unknown> = {
            flight_option_id: flight.id,
            slider_position: sliderValue,
            justification_note: justification || undefined,
          };
          // For synthetic DB1B flights, send full flight data so backend can persist
          if (typeof flight.id === "string" && flight.id.startsWith("db1b-")) {
            payload.synthetic_flight = {
              airline_code: flight.airline_code,
              airline_name: flight.airline_name,
              origin_airport: flight.origin_airport,
              destination_airport: flight.destination_airport,
              departure_time: flight.departure_time,
              arrival_time: flight.arrival_time,
              duration_minutes: flight.duration_minutes || 0,
              stops: flight.stops,
              price: flight.price,
              currency: flight.currency || "USD",
              cabin_class: flight.cabin_class || null,
            };
          }
          await apiClient.post(`/search/${leg.id}/select`, payload);
        }
      }
      // Persist the analysis snapshot so review/approval pages can show what alternatives were presented
      if (justificationAnalysis) {
        try {
          await apiClient.post(`/trips/${tripId}/save-analysis-snapshot`, {
            legs: justificationAnalysis.legs,
            trip_totals: justificationAnalysis.trip_totals,
            trip_window_alternatives: justificationAnalysis.trip_window_alternatives,
          });
        } catch {
          // Non-critical — review page can still fall back to live fetch
        }
      }

      setJustificationAnalysis(null);
      setHasSwitched(false);
      setConfirmed(true);

      // Navigate to the review & submit page for manager approval
      navigate(`/trips/${tripId}/review`);
    } catch {
      alert("Failed to save your flight selection. Please try again.");
    } finally {
      setConfirming(false);
    }
  }

  if (tripLoading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="h-4 w-64 bg-muted animate-pulse rounded" />
        <div className="h-40 bg-muted animate-pulse rounded-lg" />
      </div>
    );
  }

  if (!currentTrip) {
    return (
      <div className="text-center py-12 space-y-3">
        <p className="text-muted-foreground">Trip not found.</p>
        <Link to="/trips">
          <Button variant="outline">Back to My Trips</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Trip header */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Link
            to="/trips"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            My Trips
          </Link>
          <span className="text-muted-foreground">/</span>
          <span className="text-sm font-medium">{currentTrip.title}</span>
        </div>
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold tracking-tight">Flight Search</h2>
          <span className="text-xs font-medium text-muted-foreground bg-muted rounded-md px-2 py-0.5">
            All prices in USD
          </span>
        </div>
      </div>

      {/* Trip Cost Bar — shows total across all legs with comparisons */}
      {currentTrip.legs.length > 1 && tripId && (
        <TripCostBar
          tripId={tripId}
          legs={currentTrip.legs}
          selectedFlights={selectedFlights}
          results={results}
          activeLegIndex={activeLegIndex}
          onLegClick={(i) => { setActiveLegIndex(i); setUserSwitchedLeg(true); }}
        />
      )}

      {/* Leg tabs (only if no TripCostBar, i.e. single leg) */}
      {currentTrip.legs.length === 1 && null}
      {currentTrip.legs.length > 1 && !Object.keys(selectedFlights).length && (
        <div className="flex gap-2">
          {currentTrip.legs.map((leg, i) => (
            <button
              key={leg.id}
              onClick={() => { setActiveLegIndex(i); setUserSwitchedLeg(true); }}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                i === activeLegIndex
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
              }`}
            >
              Leg {i + 1}: {leg.origin_airport} &rarr;{" "}
              {leg.destination_airport}
            </button>
          ))}
        </div>
      )}

      {/* Add return flight */}
      {currentTrip.legs.length === 1 && activeLeg && (
        <div className="rounded-md border border-border p-3">
          {!showReturnForm ? (
            <button
              type="button"
              onClick={() => setShowReturnForm(true)}
              className="text-sm text-primary hover:underline font-medium"
            >
              + Add return flight ({activeLeg.destination_city} &rarr; {activeLeg.origin_city})
            </button>
          ) : (
            <div className="flex items-end gap-3">
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">
                  Return: {activeLeg.destination_city} &rarr; {activeLeg.origin_city}
                </label>
                <Input
                  type="date"
                  value={returnDate}
                  min={activeLeg.preferred_date || undefined}
                  onChange={(e) => setReturnDate(e.target.value)}
                />
              </div>
              <Button
                size="sm"
                disabled={!returnDate || addingReturn}
                onClick={async () => {
                  if (!tripId || !returnDate) return;
                  setAddingReturn(true);
                  try {
                    await apiClient.post(`/trips/${tripId}/add-leg`, {
                      origin_city: activeLeg.destination_city,
                      destination_city: activeLeg.origin_city,
                      preferred_date: returnDate,
                      flexibility_days: activeLeg.flexibility_days,
                      cabin_class: activeLeg.cabin_class,
                      passengers: activeLeg.passengers,
                    });
                    await fetchTrip(tripId);
                    setShowReturnForm(false);
                    setReturnDate("");
                  } catch {
                    // Silently handle
                  } finally {
                    setAddingReturn(false);
                  }
                }}
              >
                {addingReturn ? "Adding..." : "Add Return"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => { setShowReturnForm(false); setReturnDate(""); }}
              >
                Cancel
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Active leg details */}
      {activeLeg && (
        <LegCard leg={activeLeg} index={activeLegIndex} />
      )}

      {/* Search button */}
      {!searchResult && !searchLoading && (
        <Button onClick={handleSearch}>
          Search Flights
        </Button>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 space-y-2">
          <p className="text-sm text-destructive font-medium">{error}</p>
          <Button size="sm" onClick={handleSearch}>
            Retry Search
          </Button>
        </div>
      )}

      {/* Loading skeleton */}
      {searchLoading && (
        <div className="space-y-4">
          <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              <span className="text-sm font-medium">
                Searching flights...
                {elapsed > 0 && <span className="text-muted-foreground ml-1">({elapsed}s)</span>}
              </span>
            </div>
            <Button variant="ghost" size="sm" onClick={cancelSearch} className="text-xs">
              Cancel
            </Button>
          </div>

          <div className="flex items-center justify-between bg-muted/30 rounded-lg px-3 py-2">
            <div className="h-3 w-64 bg-muted animate-pulse rounded" />
            <div className="h-3 w-24 bg-muted animate-pulse rounded" />
          </div>

          <div className="rounded-lg bg-muted/20 p-3 space-y-3">
            <div className="flex items-center justify-between">
              <div className="h-4 w-28 bg-muted animate-pulse rounded" />
              <div className="h-3 w-44 bg-muted animate-pulse rounded" />
            </div>
            <div className="flex gap-2 overflow-x-auto pb-2">
              {Array.from({ length: 15 }).map((_, i) => (
                <div
                  key={i}
                  className="w-[72px] h-[88px] bg-muted/60 animate-pulse rounded-lg shrink-0"
                />
              ))}
            </div>
          </div>

          <div className="h-10 bg-muted/40 animate-pulse rounded-lg" />

          <div className="space-y-2">
            <div className="h-4 w-20 bg-muted animate-pulse rounded" />
            <div className="h-5 bg-muted/40 animate-pulse rounded-full" />
          </div>

          <div className="rounded-lg bg-muted/15 p-3 space-y-2">
            <div className="h-4 w-48 bg-muted animate-pulse rounded" />
            <div className="rounded-lg border border-border overflow-hidden">
              <div className="flex bg-muted/40">
                <div className="w-[120px] h-8 shrink-0 border-r border-border" />
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="w-[68px] h-8 shrink-0 flex items-center justify-center">
                    <div className="h-3 w-12 bg-muted animate-pulse rounded" />
                  </div>
                ))}
              </div>
              {Array.from({ length: 5 }).map((_, r) => (
                <div key={r} className="flex border-t border-border/50">
                  <div className="w-[120px] h-10 shrink-0 border-r border-border flex items-center px-2">
                    <div className="h-3 w-20 bg-muted/60 animate-pulse rounded" />
                  </div>
                  {Array.from({ length: 8 }).map((_, c) => (
                    <div key={c} className="w-[68px] h-10 shrink-0 flex items-center justify-center">
                      <div className="h-5 w-10 bg-muted/40 animate-pulse rounded" />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="h-4 w-36 bg-muted animate-pulse rounded" />
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-[52px] bg-muted/30 animate-pulse rounded-md border border-border/30"
              />
            ))}
          </div>
        </div>
      )}

      {/* Search results */}
      {searchResult && !searchLoading && activeLeg && (
        <SearchResults
          result={searchResult}
          legId={activeLeg.id}
          sliderValue={sliderValue}
          sliderLoading={sliderLoading}
          onSliderChange={handleSliderChange}
          onDateSelect={() => {}}
          onFlightSelect={handleFlightSelect}
          selectedFlightId={activeLeg ? selectedFlights[activeLeg.id]?.id : undefined}
          excludedAirlines={excludedAirlines}
          dateEvents={legEventData?.date_events}
          allEvents={legEventData?.events}
          eventSummary={legEventData?.summary}
          destination={legEventData?.destination}
        />
      )}

      {/* Month Price Trend — shows price comparison across months */}
      {searchResult && !searchLoading && activeLeg && (
        <MonthPriceTrend
          legId={activeLeg.id}
          preferredDate={activeLeg.preferred_date}
        />
      )}

      {/* Hotel search — shown after flight search */}
      {searchResult && !searchLoading && activeLeg && (
        <HotelSearch
          legId={activeLeg.id}
          destinationCity={activeLeg.destination_city}
          preferredDate={activeLeg.preferred_date}
        />
      )}

      {/* Bundle optimizer — shown after flight search */}
      {searchResult && !searchLoading && activeLeg && (
        <BundleOptimizer
          legId={activeLeg.id}
          destination={activeLeg.destination_city}
        />
      )}

      {/* Selected flight confirmation bar (trip-level) */}
      {activeSelectedFlight && (
        <div className="fixed bottom-0 left-60 right-0 bg-card border-t border-border shadow-lg z-40">
          {/* Inline justification banner ($100-$500 savings) */}
          {justificationAnalysis && (justificationAnalysis.trip_totals?.savings_amount ?? justificationAnalysis.savings?.amount ?? 0) < 500 && (
            <div className="max-w-5xl mx-auto px-4 pt-3">
              <JustificationModal
                analysis={justificationAnalysis}
                confirming={confirming}
                mode="inline"
                hasSwitched={hasSwitched}
                currentTotal={Object.values(selectedFlights).reduce((s, f) => s + f.price, 0)}
                switchedFlights={selectedFlights}
                legs={currentTrip?.legs}
                onConfirm={async (justification) => {
                  await confirmAllLegs(justification);
                  setHasSwitched(false);
                }}
                onSwitch={(flightOptionId, legId) => {
                  const targetLegId = legId || activeLeg?.id;
                  if (!targetLegId) return;
                  const legResults = results[targetLegId]?.all_options || [];
                  const alt = legResults.find((f) => f.id === flightOptionId);
                  if (alt) {
                    setSelectedFlights((prev) => ({ ...prev, [targetLegId]: alt }));
                  }
                  setHasSwitched(true);
                }}
                onSwitchTripWindow={handleSwitchTripWindow}
                onCabinDowngrade={handleCabinDowngrade}
                onCancel={() => { if (hasSwitched) { setHasSwitched(false); } else { setJustificationAnalysis(null); } }}
              />
            </div>
          )}

          {/* Main selection bar */}
          <div className="max-w-5xl mx-auto flex items-center justify-between p-4">
            <div className="flex items-center gap-4">
              {/* Per-leg selection summary */}
              {totalLegs > 1 ? (
                <div className="flex items-center gap-3">
                  {currentTrip.legs.map((leg, i) => {
                    const sel = selectedFlights[leg.id];
                    return (
                      <div key={leg.id} className="text-xs">
                        <span className="text-muted-foreground">Leg {i + 1}:</span>{" "}
                        {sel ? (
                          <span className="font-medium">
                            {sel.airline_name} ${Math.round(sel.price).toLocaleString()}
                            {sel.duration_minutes > 0 && (
                              <span className="text-muted-foreground font-normal ml-1">
                                {Math.floor(sel.duration_minutes / 60)}h{sel.duration_minutes % 60 > 0 ? ` ${sel.duration_minutes % 60}m` : ""}
                                {" \u00b7 "}{sel.stops === 0 ? "Nonstop" : `${sel.stops} stop`}
                              </span>
                            )}
                          </span>
                        ) : (
                          <span className="text-muted-foreground italic">not selected</span>
                        )}
                      </div>
                    );
                  })}
                  <div className="border-l border-border pl-3">
                    <span className="text-sm font-bold">
                      Total: ${Math.round(
                        Object.values(selectedFlights).reduce((s, f) => s + f.price, 0)
                      ).toLocaleString()}
                    </span>
                    {!allLegsSelected && (
                      <span className="text-[10px] text-muted-foreground ml-1">
                        ({selectedCount}/{totalLegs} legs)
                      </span>
                    )}
                  </div>
                </div>
              ) : (
                <>
                  <div>
                    <span className="text-sm font-medium">
                      {activeSelectedFlight.airline_name}{" "}
                      {activeSelectedFlight.flight_numbers}
                    </span>
                    <span className="text-sm text-muted-foreground ml-2">
                      {activeSelectedFlight.origin_airport} &rarr;{" "}
                      {activeSelectedFlight.destination_airport}
                      {activeSelectedFlight.duration_minutes > 0 && (
                        <>
                          {" \u00b7 "}
                          {Math.floor(activeSelectedFlight.duration_minutes / 60)}h
                          {activeSelectedFlight.duration_minutes % 60 > 0 && ` ${activeSelectedFlight.duration_minutes % 60}m`}
                          {" \u00b7 "}
                          {activeSelectedFlight.stops === 0 ? "Nonstop" : `${activeSelectedFlight.stops} stop`}
                        </>
                      )}
                    </span>
                  </div>
                  <span className="text-base font-bold">
                    ${Math.round(activeSelectedFlight.price).toLocaleString()}
                  </span>
                </>
              )}

              {/* Savings context */}
              {justificationAnalysis && (justificationAnalysis.trip_totals?.savings_amount > 0 || justificationAnalysis.savings?.amount > 0) && (
                <span className={`text-xs font-medium px-2 py-0.5 rounded-md ${
                  (justificationAnalysis.trip_totals?.savings_amount ?? justificationAnalysis.savings?.amount ?? 0) >= 500
                    ? "bg-red-100 text-red-700"
                    : (justificationAnalysis.trip_totals?.savings_amount ?? justificationAnalysis.savings?.amount ?? 0) >= 200
                    ? "bg-amber-100 text-amber-700"
                    : "bg-muted text-muted-foreground"
                }`}>
                  {justificationAnalysis.trip_totals
                    ? `${formatPrice(justificationAnalysis.trip_totals.savings_amount)} trip savings available`
                    : `${formatPrice(justificationAnalysis.savings.amount)} more than cheapest`
                  }
                </span>
              )}
            </div>
            <div className="flex gap-2 items-center">
              <Button
                variant="outline"
                size="sm"
                onClick={handleClearSelection}
              >
                Clear
              </Button>
              {totalLegs > 1 && !allLegsSelected ? (
                <Button
                  size="sm"
                  onClick={() => {
                    // Jump to next unselected leg
                    const nextIdx = currentTrip.legs.findIndex((l) => !selectedFlights[l.id]);
                    if (nextIdx >= 0) {
                      setActiveLegIndex(nextIdx);
                      setUserSwitchedLeg(true);
                    }
                  }}
                >
                  Select Leg {currentTrip.legs.findIndex((l) => !selectedFlights[l.id]) + 1} &rarr;
                </Button>
              ) : confirmed ? (
                <Button
                  size="sm"
                  onClick={() => navigate(`/trips/${tripId}/review`)}
                >
                  Submit for Approval
                </Button>
              ) : (
                <Button
                  size="sm"
                  disabled={confirming || analyzing || (totalLegs > 1 && !allLegsSelected)}
                  onClick={handleConfirmTrip}
                >
                  {analyzing
                    ? "Analyzing..."
                    : confirming
                    ? "Saving..."
                    : allLegsSelected
                    ? "Confirm to Review"
                    : "Confirm Selection"}
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Trip assistant chat bubble */}
      {activeLeg && tripId && (
        <SearchAssistant
          tripId={tripId}
          activeLeg={activeLeg}
          legsCount={currentTrip.legs.length}
          onTripUpdated={handleTripUpdated}
        />
      )}

      {/* Full justification modal (>$500 savings) */}
      {justificationAnalysis && (justificationAnalysis.trip_totals?.savings_amount ?? justificationAnalysis.savings?.amount ?? 0) >= 500 && activeSelectedFlight && (
        <JustificationModal
          analysis={justificationAnalysis}
          confirming={confirming}
          mode="modal"
          hasSwitched={hasSwitched}
          currentTotal={Object.values(selectedFlights).reduce((s, f) => s + f.price, 0)}
          switchedFlights={selectedFlights}
          legs={currentTrip?.legs}
          onConfirm={async (justification) => {
            await confirmAllLegs(justification);
            setHasSwitched(false);
          }}
          onSwitch={(flightOptionId, legId) => {
            const targetLegId = legId || activeLeg?.id;
            if (!targetLegId) return;
            const legResults = results[targetLegId]?.all_options || [];
            const alt = legResults.find((f) => f.id === flightOptionId);
            if (alt) {
              setSelectedFlights((prev) => ({ ...prev, [targetLegId]: alt }));
            }
            setHasSwitched(true);
          }}
          onSwitchTripWindow={handleSwitchTripWindow}
          onCabinDowngrade={handleCabinDowngrade}
          onCancel={() => { if (hasSwitched) { setHasSwitched(false); } else { setJustificationAnalysis(null); } }}
        />
      )}
    </div>
  );
}
