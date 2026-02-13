import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useHotelStore } from "@/stores/hotelStore";
import { HotelOptionCard } from "./HotelOptionCard";
import { HotelAreaComparison } from "./HotelAreaComparison";
import { HotelPriceCalendar } from "./HotelPriceCalendar";
import { HotelEventWarning } from "./HotelEventWarning";
import type { HotelOption, HotelSearchResult } from "@/types/hotel";

interface Props {
  legId: string;
  destinationCity: string;
  preferredDate: string;
}

export function HotelSearch({ legId, destinationCity, preferredDate }: Props) {
  const { results, loading, error, searchHotels, selectHotel } = useHotelStore();
  const result = results[legId] as HotelSearchResult | undefined;

  const [checkIn, setCheckIn] = useState(preferredDate);
  const [checkOut, setCheckOut] = useState(() => {
    const d = new Date(preferredDate + "T12:00:00");
    d.setDate(d.getDate() + 3);
    return d.toISOString().split("T")[0];
  });
  const [guests, setGuests] = useState(1);
  const [showAll, setShowAll] = useState(false);
  const [selectedHotel, setSelectedHotel] = useState<HotelOption | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [sortBy, setSortBy] = useState("value");

  function handleSearch() {
    searchHotels(legId, checkIn, checkOut, guests, null, null, sortBy);
  }

  async function handleSelect(hotel: HotelOption) {
    setSelectedHotel(hotel);
    setSelecting(true);
    try {
      await selectHotel(legId, hotel.id, checkIn, checkOut);
    } finally {
      setSelecting(false);
    }
  }

  const displayOptions = result
    ? showAll
      ? result.all_options
      : result.all_options.slice(0, 5)
    : [];

  return (
    <div className="space-y-5 rounded-lg border border-border p-5">
      <h3 className="text-sm font-semibold">
        Hotel Search — {destinationCity}
      </h3>

      {/* Search form */}
      <div className="flex items-end gap-3 flex-wrap">
        <div>
          <label className="text-xs text-muted-foreground block mb-1">
            Check-in
          </label>
          <input
            type="date"
            value={checkIn}
            onChange={(e) => setCheckIn(e.target.value)}
            className="px-2 py-1.5 rounded-md border border-input text-sm bg-background"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">
            Check-out
          </label>
          <input
            type="date"
            value={checkOut}
            onChange={(e) => setCheckOut(e.target.value)}
            className="px-2 py-1.5 rounded-md border border-input text-sm bg-background"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">
            Guests
          </label>
          <input
            type="number"
            min={1}
            max={4}
            value={guests}
            onChange={(e) => setGuests(Number(e.target.value))}
            className="w-16 px-2 py-1.5 rounded-md border border-input text-sm bg-background"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">
            Sort by
          </label>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="px-2 py-1.5 rounded-md border border-input text-sm bg-background"
          >
            <option value="value">Best Value</option>
            <option value="price">Price</option>
            <option value="rating">Rating</option>
            <option value="distance">Distance</option>
          </select>
        </div>
        <Button onClick={handleSearch} disabled={loading} size="sm">
          {loading ? "Searching..." : "Search Hotels"}
        </Button>
      </div>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-24 bg-muted animate-pulse rounded-lg" />
          ))}
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div className="space-y-5">
          {/* Metadata */}
          <div className="text-xs text-muted-foreground">
            {result.metadata.total_options} hotels found in {result.destination}
            {result.metadata.cheapest_rate && (
              <> &middot; From ${Math.round(result.metadata.cheapest_rate)}/night</>
            )}
          </div>

          {/* Event warnings */}
          <HotelEventWarning warnings={result.event_warnings} />

          {/* Hotel price calendar */}
          <HotelPriceCalendar calendar={result.price_calendar} />

          {/* Recommendation */}
          {result.recommendation && (
            <div>
              <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                Recommended
              </h4>
              <HotelOptionCard
                hotel={result.recommendation}
                isRecommended
                onSelect={handleSelect}
              />
            </div>
          )}

          {/* Area comparison */}
          <HotelAreaComparison areas={result.area_comparison} />

          {/* All options */}
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              All Hotels ({result.all_options.length})
            </h4>
            {displayOptions.map((hotel) => (
              <HotelOptionCard
                key={hotel.id}
                hotel={hotel}
                onSelect={handleSelect}
              />
            ))}
            {result.all_options.length > 5 && (
              <button
                type="button"
                onClick={() => setShowAll(!showAll)}
                className="text-sm text-primary hover:underline"
              >
                {showAll
                  ? "Show less"
                  : `Show all ${result.all_options.length} hotels`}
              </button>
            )}
          </div>

          {/* Selection confirmation */}
          {selectedHotel && (
            <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
              {selecting
                ? "Saving selection..."
                : `Selected: ${selectedHotel.hotel_name} — $${Math.round(selectedHotel.nightly_rate)}/night ($${Math.round(selectedHotel.total_rate)} total)`}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
