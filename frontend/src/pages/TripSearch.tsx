import { useCallback, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useTripStore } from "@/stores/tripStore";
import { useSearchStore } from "@/stores/searchStore";
import { useEventStore } from "@/stores/eventStore";
import { SearchResults } from "@/components/search/SearchResults";
import { HotelSearch } from "@/components/hotel/HotelSearch";
import { BundleOptimizer } from "@/components/bundle/BundleOptimizer";
import { LegCard } from "@/components/trip/LegCard";
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
    searchLeg,
    rescoreWithSlider,
  } = useSearchStore();
  const { legEvents, fetchLegEvents } = useEventStore();

  const [activeLegIndex, setActiveLegIndex] = useState(0);
  const [selectedFlight, setSelectedFlight] = useState<FlightOption | null>(
    null
  );
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    if (tripId) {
      fetchTrip(tripId);
    }
  }, [tripId, fetchTrip]);

  const activeLeg = currentTrip?.legs[activeLegIndex];
  const searchResult = activeLeg ? results[activeLeg.id] : null;
  const legEventData = activeLeg ? legEvents[activeLeg.id] : null;

  // Auto-search when leg becomes active and hasn't been searched yet
  useEffect(() => {
    if (activeLeg && !results[activeLeg.id] && !searchLoading) {
      searchLeg(activeLeg.id);
    }
  }, [activeLeg, results, searchLoading, searchLeg]);

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

  function handleDateSelect(date: string) {
    console.log("Date selected:", date);
  }

  function handleFlightSelect(flight: FlightOption) {
    setSelectedFlight(flight);
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
              onClick={() => setActiveLegIndex(i)}
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

      {/* Active leg details */}
      {activeLeg && (
        <LegCard leg={activeLeg} index={activeLegIndex} />
      )}

      {/* Search button */}
      {!searchResult && (
        <Button onClick={handleSearch} disabled={searchLoading}>
          {searchLoading ? "Searching..." : "Search Flights"}
        </Button>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
          <Button
            variant="outline"
            size="sm"
            className="ml-3"
            onClick={handleSearch}
          >
            Retry
          </Button>
        </div>
      )}

      {/* Loading skeleton */}
      {searchLoading && (
        <div className="space-y-6">
          {/* Metadata skeleton */}
          <div className="flex items-center justify-between">
            <div className="h-3 w-64 bg-muted animate-pulse rounded" />
            <div className="h-3 w-24 bg-muted animate-pulse rounded" />
          </div>

          {/* Price calendar skeleton */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="h-4 w-28 bg-muted animate-pulse rounded" />
              <div className="h-3 w-44 bg-muted animate-pulse rounded" />
            </div>
            <div className="flex gap-2 overflow-x-auto pb-2">
              {Array.from({ length: 15 }).map((_, i) => (
                <div
                  key={i}
                  className="w-[72px] h-[88px] bg-muted animate-pulse rounded-lg shrink-0"
                />
              ))}
            </div>
          </div>

          {/* Slider skeleton */}
          <div className="space-y-2">
            <div className="h-4 w-20 bg-muted animate-pulse rounded" />
            <div className="h-5 bg-muted animate-pulse rounded-full" />
          </div>

          {/* Recommendation skeleton */}
          <div className="space-y-2">
            <div className="h-4 w-28 bg-muted animate-pulse rounded" />
            <div className="h-28 bg-muted animate-pulse rounded-lg border border-primary/20" />
          </div>

          {/* Flight cards skeleton */}
          <div className="space-y-2">
            <div className="h-4 w-36 bg-muted animate-pulse rounded" />
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-20 bg-muted animate-pulse rounded-lg"
              />
            ))}
          </div>
        </div>
      )}

      {/* Search results */}
      {searchResult && !searchLoading && (
        <SearchResults
          result={searchResult}
          sliderValue={sliderValue}
          sliderLoading={sliderLoading}
          onSliderChange={handleSliderChange}
          onDateSelect={handleDateSelect}
          onFlightSelect={handleFlightSelect}
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

      {/* Selected flight confirmation */}
      {selectedFlight && (
        <div className="fixed bottom-0 left-60 right-0 bg-card border-t border-border p-4 shadow-lg">
          <div className="max-w-5xl mx-auto flex items-center justify-between">
            <div>
              <span className="text-sm font-medium">
                Selected: {selectedFlight.airline_name}{" "}
                {selectedFlight.flight_numbers}
              </span>
              <span className="text-sm text-muted-foreground ml-3">
                ${Math.round(selectedFlight.price)} &middot;{" "}
                {selectedFlight.origin_airport} &rarr;{" "}
                {selectedFlight.destination_airport}
              </span>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelectedFlight(null)}
              >
                Clear
              </Button>
              <Button
                size="sm"
                disabled={confirming}
                onClick={async () => {
                  if (!activeLeg || !selectedFlight?.id) return;
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
                    // Selection failed silently — flight still shown as selected
                  } finally {
                    setConfirming(false);
                  }
                }}
              >
                {confirming ? "Saving..." : confirmed ? "Confirmed!" : "Confirm Selection"}
              </Button>
              {confirmed && tripId && (
                <Link to={`/trips/${tripId}/review`}>
                  <Button variant="outline" className="ml-2">
                    Review & Submit
                  </Button>
                </Link>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
