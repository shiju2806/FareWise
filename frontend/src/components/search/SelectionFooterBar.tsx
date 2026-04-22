import type { RefObject } from "react";
import { Button } from "@/components/ui/button";
import { JustificationModal } from "@/components/search/JustificationModal";
import { formatPrice } from "@/lib/currency";
import type { FlightOption } from "@/types/flight";
import type { Trip, TripLeg } from "@/types/trip";
import type { SearchResult, TripWindowProposal } from "@/types/search";

interface HotelTotal {
  total: number;
  nightly: number;
  nights: number;
  name: string;
  currency: string;
}

interface Props {
  trip: Trip;
  tripId: string;
  activeLeg: TripLeg;
  activeSelectedFlight: FlightOption;
  selectedFlights: Record<string, FlightOption>;
  results: Record<string, SearchResult>;
  hotelDates: { checkIn: string; checkOut: string } | null;
  hotelSelections: Record<string, string>;
  selectedHotelTotal: HotelTotal | null;
  hotelSectionRef: RefObject<HTMLDivElement>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  justificationAnalysis: any;
  confirming: boolean;
  analyzing: boolean;
  confirmed: boolean;
  hasSwitched: boolean;
  onClearSelection: () => void;
  onJumpToLeg: (index: number) => void;
  onConfirmTrip: () => void;
  onNavigateReview: () => void;
  onSetSelection: (legId: string, flight: FlightOption) => void;
  onSetHasSwitched: (v: boolean) => void;
  onDismissJustification: () => void;
  onConfirmAllLegs: (justification?: string) => Promise<void>;
  onSwitchTripWindow: (proposal: TripWindowProposal) => void;
  onCabinDowngrade: (cabin: string) => Promise<void>;
}

export function SelectionFooterBar({
  trip,
  tripId,
  activeLeg,
  activeSelectedFlight,
  selectedFlights,
  results,
  hotelDates,
  hotelSelections,
  selectedHotelTotal,
  hotelSectionRef,
  justificationAnalysis,
  confirming,
  analyzing,
  confirmed,
  hasSwitched,
  onClearSelection,
  onJumpToLeg,
  onConfirmTrip,
  onNavigateReview,
  onSetSelection,
  onSetHasSwitched,
  onDismissJustification,
  onConfirmAllLegs,
  onSwitchTripWindow,
  onCabinDowngrade,
}: Props) {
  const totalLegs = trip.legs.length;
  const selectedCount = Object.keys(selectedFlights).length;
  const allLegsSelected = selectedCount === totalLegs && totalLegs > 0;
  const inlineJustification =
    justificationAnalysis &&
    (justificationAnalysis.trip_totals?.savings_amount ??
      justificationAnalysis.savings?.amount ??
      0) < 500;

  const handleJustificationSwitch = (flightOptionId: string, legId?: string) => {
    const targetLegId = legId || activeLeg.id;
    const legResults = results[targetLegId]?.all_options || [];
    const alt = legResults.find((f) => f.id === flightOptionId);
    if (alt) onSetSelection(targetLegId, alt);
    onSetHasSwitched(true);
  };

  const handleJustificationCancel = () => {
    if (hasSwitched) {
      onSetHasSwitched(false);
    } else {
      onDismissJustification();
    }
  };

  void tripId; // reserved for future per-trip actions

  return (
    <div className="fixed bottom-0 left-60 right-0 bg-card border-t border-border shadow-lg z-40">
      {inlineJustification && (
        <div className="max-w-5xl mx-auto px-4 pt-3">
          <JustificationModal
            analysis={justificationAnalysis}
            confirming={confirming}
            mode="inline"
            hasSwitched={hasSwitched}
            currentTotal={Object.values(selectedFlights).reduce((s, f) => s + f.price, 0)}
            switchedFlights={selectedFlights}
            legs={trip.legs}
            onConfirm={async (justification) => {
              await onConfirmAllLegs(justification);
              onSetHasSwitched(false);
            }}
            onSwitch={handleJustificationSwitch}
            onSwitchTripWindow={onSwitchTripWindow}
            onCabinDowngrade={onCabinDowngrade}
            onCancel={handleJustificationCancel}
          />
        </div>
      )}

      <div className="max-w-5xl mx-auto flex items-center justify-between p-4">
        <div className="flex items-center gap-4">
          {totalLegs > 1 ? (
            <div className="flex items-center gap-3">
              {trip.legs.map((leg, i) => {
                const sel = selectedFlights[leg.id];
                return (
                  <div key={leg.id} className="text-xs">
                    <span className="text-muted-foreground">Leg {i + 1}:</span>{" "}
                    {sel ? (
                      <span className="font-medium">
                        {sel.airline_name} ${Math.round(sel.price).toLocaleString()}
                        {sel.duration_minutes > 0 && (
                          <span className="text-muted-foreground font-normal ml-1">
                            {Math.floor(sel.duration_minutes / 60)}h
                            {sel.duration_minutes % 60 > 0 ? ` ${sel.duration_minutes % 60}m` : ""}
                            {" \u00b7 "}
                            {sel.stops === 0 ? "Nonstop" : `${sel.stops} stop`}
                          </span>
                        )}
                      </span>
                    ) : (
                      <span className="text-muted-foreground italic">not selected</span>
                    )}
                  </div>
                );
              })}
              <div className="border-l border-border pl-3 space-y-0.5">
                {(() => {
                  const flightTotal = Math.round(
                    Object.values(selectedFlights).reduce((s, f) => s + f.price, 0)
                  );
                  const hotelTotal = selectedHotelTotal ? Math.round(selectedHotelTotal.total) : 0;
                  const grandTotal = flightTotal + hotelTotal;
                  return (
                    <>
                      <div className="text-[10px] text-muted-foreground leading-tight">
                        Flights: ${flightTotal.toLocaleString()}
                        {selectedHotelTotal && (
                          <>
                            {" "}&middot; Hotel: ${hotelTotal.toLocaleString()}{" "}
                            <span className="text-muted-foreground/70">
                              ({selectedHotelTotal.nights}n)
                            </span>
                          </>
                        )}
                      </div>
                      <div className="text-sm font-bold leading-tight">
                        {selectedHotelTotal
                          ? `Trip Total: $${grandTotal.toLocaleString()}`
                          : `Total: $${flightTotal.toLocaleString()}`}
                      </div>
                    </>
                  );
                })()}
                {!allLegsSelected && (
                  <span className="text-[10px] text-muted-foreground">
                    ({selectedCount}/{totalLegs} legs)
                  </span>
                )}
              </div>
            </div>
          ) : (
            <>
              <div>
                <span className="text-sm font-medium">
                  {activeSelectedFlight.airline_name} {activeSelectedFlight.flight_numbers}
                </span>
                <span className="text-sm text-muted-foreground ml-2">
                  {activeSelectedFlight.origin_airport} &rarr;{" "}
                  {activeSelectedFlight.destination_airport}
                  {activeSelectedFlight.duration_minutes > 0 && (
                    <>
                      {" \u00b7 "}
                      {Math.floor(activeSelectedFlight.duration_minutes / 60)}h
                      {activeSelectedFlight.duration_minutes % 60 > 0 &&
                        ` ${activeSelectedFlight.duration_minutes % 60}m`}
                      {" \u00b7 "}
                      {activeSelectedFlight.stops === 0
                        ? "Nonstop"
                        : `${activeSelectedFlight.stops} stop`}
                    </>
                  )}
                </span>
              </div>
              <span className="text-base font-bold">
                ${Math.round(activeSelectedFlight.price).toLocaleString()}
              </span>
            </>
          )}

          {justificationAnalysis &&
            (justificationAnalysis.trip_totals?.savings_amount > 0 ||
              justificationAnalysis.savings?.amount > 0) && (
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-md ${
                  (justificationAnalysis.trip_totals?.savings_amount ??
                    justificationAnalysis.savings?.amount ??
                    0) >= 500
                    ? "bg-red-100 text-red-700"
                    : (justificationAnalysis.trip_totals?.savings_amount ??
                        justificationAnalysis.savings?.amount ??
                        0) >= 200
                    ? "bg-amber-100 text-amber-700"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {justificationAnalysis.trip_totals
                  ? `${formatPrice(justificationAnalysis.trip_totals.savings_amount)} trip savings available`
                  : `${formatPrice(justificationAnalysis.savings.amount)} more than cheapest`}
              </span>
            )}

          {hotelDates &&
            (hotelSelections[trip.legs[0]?.id] ? (
              <span className="text-xs font-medium px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-700">
                &#10003; {selectedHotelTotal?.name || "Hotel booked"}
              </span>
            ) : (
              <span
                className="text-xs font-medium px-2 py-0.5 rounded-md bg-blue-100 text-blue-700 cursor-pointer hover:bg-blue-200 transition-colors"
                onClick={() =>
                  hotelSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
                }
              >
                Hotel not selected
              </span>
            ))}
        </div>
        <div className="flex gap-2 items-center">
          <Button variant="outline" size="sm" onClick={onClearSelection}>
            Clear
          </Button>
          {totalLegs > 1 && !allLegsSelected ? (
            <Button
              size="sm"
              onClick={() => {
                const nextIdx = trip.legs.findIndex((l) => !selectedFlights[l.id]);
                if (nextIdx >= 0) onJumpToLeg(nextIdx);
              }}
            >
              Select Leg {trip.legs.findIndex((l) => !selectedFlights[l.id]) + 1} &rarr;
            </Button>
          ) : confirmed ? (
            <Button size="sm" onClick={onNavigateReview}>
              Submit for Approval
            </Button>
          ) : (
            <Button
              size="sm"
              disabled={confirming || analyzing || (totalLegs > 1 && !allLegsSelected)}
              onClick={onConfirmTrip}
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
  );
}
