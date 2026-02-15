import { useCallback, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useTripStore } from "@/stores/tripStore";
import { useSearchStore } from "@/stores/searchStore";
import { useEventStore } from "@/stores/eventStore";
import { SearchResults } from "@/components/search/SearchResults";
import { JustificationModal } from "@/components/search/JustificationModal";
import { HotelSearch } from "@/components/hotel/HotelSearch";
import { BundleOptimizer } from "@/components/bundle/BundleOptimizer";
import { LegCard } from "@/components/trip/LegCard";
import { SearchAssistant } from "@/components/search/SearchAssistant";
import type { FlightOption } from "@/types/flight";
import apiClient from "@/api/client";

export default function TripSearch() {
  const { tripId } = useParams<{ tripId: string }>();
  const { currentTrip, loading: tripLoading, fetchTrip } = useTripStore();
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
  } = useSearchStore();
  const { legEvents, fetchLegEvents } = useEventStore();

  const [activeLegIndex, setActiveLegIndex] = useState(0);
  const [selectedFlight, setSelectedFlight] = useState<FlightOption | null>(
    null
  );
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [showReturnForm, setShowReturnForm] = useState(false);
  const [returnDate, setReturnDate] = useState("");
  const [addingReturn, setAddingReturn] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [justificationAnalysis, setJustificationAnalysis] = useState<any>(null);
  const [analyzing, setAnalyzing] = useState(false);
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

  // Auto-search active leg on initial load (skips if results exist from cache)
  const [autoSearched, setAutoSearched] = useState(false);
  useEffect(() => {
    if (currentTrip && !autoSearched && !searchLoading) {
      setAutoSearched(true);
      // Only search legs that don't have cached results
      for (const leg of currentTrip.legs) {
        if (!results[leg.id]) {
          searchLeg(leg.id);
          break;
        }
      }
    }
  }, [currentTrip, autoSearched, searchLoading, results, searchLeg]);

  // Auto-search when user manually switches to a leg that hasn't been searched
  const [userSwitchedLeg, setUserSwitchedLeg] = useState(false);
  useEffect(() => {
    if (userSwitchedLeg && activeLeg && !results[activeLeg.id] && !searchLoading) {
      setUserSwitchedLeg(false);
      searchLeg(activeLeg.id);
    }
  }, [userSwitchedLeg, activeLeg, results, searchLoading, searchLeg]);

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

  function handleDateSelect(_date: string) {
    // Date filtering is handled inside SearchResults component
  }

  function handleFlightSelect(flight: FlightOption) {
    setSelectedFlight(flight);
  }

  function handleTripUpdated() {
    if (tripId) fetchTrip(tripId);
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
        <h2 className="text-2xl font-bold tracking-tight">Flight Search</h2>
      </div>

      {/* Leg tabs */}
      {currentTrip.legs.length > 1 && (
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
                    // Refresh trip to pick up the new leg
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
          {/* Search progress bar */}
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

          {/* Metadata skeleton */}
          <div className="flex items-center justify-between bg-muted/30 rounded-lg px-3 py-2">
            <div className="h-3 w-64 bg-muted animate-pulse rounded" />
            <div className="h-3 w-24 bg-muted animate-pulse rounded" />
          </div>

          {/* Price calendar skeleton */}
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

          {/* Advisor banner skeleton */}
          <div className="h-10 bg-muted/40 animate-pulse rounded-lg" />

          {/* Slider skeleton */}
          <div className="space-y-2">
            <div className="h-4 w-20 bg-muted animate-pulse rounded" />
            <div className="h-5 bg-muted/40 animate-pulse rounded-full" />
          </div>

          {/* Matrix skeleton */}
          <div className="rounded-lg bg-muted/15 p-3 space-y-2">
            <div className="h-4 w-48 bg-muted animate-pulse rounded" />
            <div className="rounded-lg border border-border overflow-hidden">
              {/* Header row */}
              <div className="flex bg-muted/40">
                <div className="w-[120px] h-8 shrink-0 border-r border-border" />
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="w-[68px] h-8 shrink-0 flex items-center justify-center">
                    <div className="h-3 w-12 bg-muted animate-pulse rounded" />
                  </div>
                ))}
              </div>
              {/* Data rows */}
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

          {/* Flight cards skeleton */}
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
          onDateSelect={handleDateSelect}
          onFlightSelect={handleFlightSelect}
          excludedAirlines={excludedAirlines}
          dateEvents={legEventData?.date_events}
          allEvents={legEventData?.events}
          eventSummary={legEventData?.summary}
          destination={legEventData?.destination}
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

      {/* Selected flight confirmation bar */}
      {selectedFlight && (
        <div className="fixed bottom-0 left-60 right-0 bg-card border-t border-border shadow-lg z-40">
          {/* Inline justification banner ($100-$500 savings) */}
          {justificationAnalysis && justificationAnalysis.savings.amount < 500 && (
            <div className="max-w-5xl mx-auto px-4 pt-3">
              <JustificationModal
                analysis={justificationAnalysis}
                confirming={confirming}
                mode="inline"
                onConfirm={async (justification) => {
                  if (!activeLeg || !selectedFlight?.id) return;
                  setConfirming(true);
                  try {
                    await apiClient.post(`/search/${activeLeg.id}/select`, {
                      flight_option_id: selectedFlight.id,
                      slider_position: sliderValue,
                      justification_note: justification,
                    });
                    setJustificationAnalysis(null);
                    setConfirmed(true);
                    setTimeout(() => {
                      setConfirmed(false);
                      setSelectedFlight(null);
                    }, 2000);
                  } catch {
                    // Selection failed silently
                  } finally {
                    setConfirming(false);
                  }
                }}
                onSwitch={(flightOptionId) => {
                  const alt = searchResult?.all_options.find(
                    (f) => f.id === flightOptionId
                  );
                  if (alt) setSelectedFlight(alt);
                  setJustificationAnalysis(null);
                }}
                onCancel={() => setJustificationAnalysis(null)}
              />
            </div>
          )}

          {/* Main selection bar */}
          <div className="max-w-5xl mx-auto flex items-center justify-between p-4">
            <div className="flex items-center gap-4">
              <div>
                <span className="text-sm font-medium">
                  {selectedFlight.airline_name}{" "}
                  {selectedFlight.flight_numbers}
                </span>
                <span className="text-sm text-muted-foreground ml-2">
                  {selectedFlight.origin_airport} &rarr;{" "}
                  {selectedFlight.destination_airport}
                </span>
              </div>
              <span className="text-base font-bold">
                ${Math.round(selectedFlight.price).toLocaleString()}
              </span>
              {/* Savings context */}
              {justificationAnalysis && justificationAnalysis.savings.amount > 0 && (
                <span className={`text-xs font-medium px-2 py-0.5 rounded-md ${
                  justificationAnalysis.savings.amount >= 500
                    ? "bg-red-100 text-red-700"
                    : justificationAnalysis.savings.amount >= 200
                    ? "bg-amber-100 text-amber-700"
                    : "bg-muted text-muted-foreground"
                }`}>
                  ${Math.round(justificationAnalysis.savings.amount).toLocaleString()} more than cheapest
                </span>
              )}
            </div>
            <div className="flex gap-2 items-center">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSelectedFlight(null);
                  setJustificationAnalysis(null);
                }}
              >
                Clear
              </Button>
              <Button
                size="sm"
                disabled={confirming || analyzing}
                onClick={async () => {
                  if (!activeLeg || !selectedFlight?.id) return;
                  // Analyze the selection for justification
                  setAnalyzing(true);
                  try {
                    const res = await apiClient.post(
                      `/search/${activeLeg.id}/analyze-selection`,
                      { flight_option_id: selectedFlight.id }
                    );
                    if (res.data.justification_required) {
                      setJustificationAnalysis(res.data);
                      setAnalyzing(false);
                      return;
                    }
                  } catch {
                    // If analysis fails, proceed without justification
                  }
                  setAnalyzing(false);

                  // No justification needed — confirm directly
                  setConfirming(true);
                  try {
                    await apiClient.post(`/search/${activeLeg.id}/select`, {
                      flight_option_id: selectedFlight.id,
                      slider_position: sliderValue,
                    });
                    setConfirmed(true);
                    setTimeout(() => {
                      setConfirmed(false);
                      setSelectedFlight(null);
                    }, 2000);
                  } catch {
                    // Selection failed silently
                  } finally {
                    setConfirming(false);
                  }
                }}
              >
                {analyzing
                  ? "Analyzing..."
                  : confirming
                  ? "Saving..."
                  : confirmed
                  ? "Confirmed!"
                  : "Confirm Selection"}
              </Button>
              {confirmed && tripId && (
                <Link to={`/trips/${tripId}/review`}>
                  <Button variant="outline" size="sm">
                    Review & Submit
                  </Button>
                </Link>
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
      {justificationAnalysis && justificationAnalysis.savings.amount >= 500 && selectedFlight && (
        <JustificationModal
          analysis={justificationAnalysis}
          confirming={confirming}
          mode="modal"
          onConfirm={async (justification) => {
            if (!activeLeg || !selectedFlight?.id) return;
            setConfirming(true);
            try {
              await apiClient.post(`/search/${activeLeg.id}/select`, {
                flight_option_id: selectedFlight.id,
                slider_position: sliderValue,
                justification_note: justification,
              });
              setJustificationAnalysis(null);
              setConfirmed(true);
              setTimeout(() => {
                setConfirmed(false);
                setSelectedFlight(null);
              }, 2000);
            } catch {
              // Selection failed silently
            } finally {
              setConfirming(false);
            }
          }}
          onSwitch={(flightOptionId) => {
            const alt = searchResult?.all_options.find(
              (f) => f.id === flightOptionId
            );
            if (alt) setSelectedFlight(alt);
            setJustificationAnalysis(null);
          }}
          onCancel={() => setJustificationAnalysis(null)}
        />
      )}
    </div>
  );
}
