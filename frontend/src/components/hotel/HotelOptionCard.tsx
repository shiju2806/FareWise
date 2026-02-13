import type { HotelOption } from "@/types/hotel";
import { Button } from "@/components/ui/button";

interface Props {
  hotel: HotelOption;
  isRecommended?: boolean;
  onSelect?: (hotel: HotelOption) => void;
}

const cancelLabels: Record<string, string> = {
  free_cancellation: "Free cancellation",
  non_refundable: "Non-refundable",
  "24h_cancellation": "24h cancellation",
};

export function HotelOptionCard({ hotel, isRecommended, onSelect }: Props) {
  const stars = hotel.star_rating
    ? "\u2B50".repeat(Math.floor(hotel.star_rating))
    : "";

  return (
    <div
      className={`rounded-lg border p-4 flex items-start gap-4 transition-colors hover:bg-accent/30 ${
        isRecommended ? "border-primary/50 bg-primary/5" : "border-border"
      }`}
    >
      {/* Hotel info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-semibold truncate">{hotel.hotel_name}</h4>
          {hotel.is_preferred_vendor && (
            <span className="px-1.5 py-0.5 text-[9px] font-medium bg-blue-100 text-blue-700 rounded">
              Preferred
            </span>
          )}
          {isRecommended && (
            <span className="px-1.5 py-0.5 text-[9px] font-medium bg-emerald-100 text-emerald-700 rounded">
              Recommended
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
          {stars && <span>{stars}</span>}
          {hotel.hotel_chain && <span>{hotel.hotel_chain}</span>}
          {hotel.neighborhood && <span>{hotel.neighborhood}</span>}
          {hotel.distance_km && <span>{hotel.distance_km} km away</span>}
        </div>

        <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground">
          {hotel.room_type && <span>{hotel.room_type}</span>}
          {hotel.cancellation_policy && (
            <span
              className={
                hotel.cancellation_policy === "free_cancellation"
                  ? "text-emerald-600"
                  : ""
              }
            >
              {cancelLabels[hotel.cancellation_policy] || hotel.cancellation_policy}
            </span>
          )}
          {hotel.user_rating && (
            <span className="font-medium text-foreground">
              {hotel.user_rating}/5
            </span>
          )}
        </div>

        {/* Amenities */}
        {hotel.amenities.length > 0 && (
          <div className="flex gap-1.5 mt-2 flex-wrap">
            {hotel.amenities.slice(0, 5).map((a) => (
              <span
                key={a}
                className="px-1.5 py-0.5 text-[9px] bg-muted rounded capitalize"
              >
                {a.replace("_", " ")}
              </span>
            ))}
            {hotel.amenities.length > 5 && (
              <span className="text-[9px] text-muted-foreground">
                +{hotel.amenities.length - 5} more
              </span>
            )}
          </div>
        )}
      </div>

      {/* Price + action */}
      <div className="text-right shrink-0">
        <p className="text-lg font-bold">${Math.round(hotel.nightly_rate)}</p>
        <p className="text-[10px] text-muted-foreground">per night</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          ${Math.round(hotel.total_rate)} total
        </p>
        {hotel.score !== undefined && (
          <p className="text-[10px] text-muted-foreground mt-0.5">
            Score: {(hotel.score * 100).toFixed(0)}
          </p>
        )}
        {onSelect && (
          <Button
            size="sm"
            variant="outline"
            className="mt-2"
            onClick={() => onSelect(hotel)}
          >
            Select
          </Button>
        )}
      </div>
    </div>
  );
}
