import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { NaturalLanguageInput } from "@/components/trip/NaturalLanguageInput";
import { StructuredTripForm } from "@/components/trip/StructuredTripForm";
import { LegList } from "@/components/trip/LegList";
import { Button } from "@/components/ui/button";
import { useTripStore, type LegInput } from "@/stores/tripStore";

type Mode = "nl" | "structured";

export default function NewTrip() {
  const navigate = useNavigate();
  const { currentTrip, loading, error, createTripNL, createTripStructured, clearError } =
    useTripStore();
  const [mode, setMode] = useState<Mode>("nl");

  async function handleNLSubmit(input: string) {
    clearError();
    const trip = await createTripNL(input);
    if (trip.legs.length === 0) {
      // Low confidence parse — switch to structured mode
      setMode("structured");
    }
  }

  async function handleStructuredSubmit(legs: LegInput[]) {
    clearError();
    await createTripStructured(legs);
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Plan a Trip</h2>
        <p className="text-muted-foreground mt-1">
          Describe your trip in natural language or fill in the form below.
        </p>
      </div>

      {/* Mode toggle */}
      <div className="flex gap-2">
        <button
          onClick={() => setMode("nl")}
          className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
            mode === "nl"
              ? "bg-primary text-primary-foreground"
              : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
          }`}
        >
          Natural Language
        </button>
        <button
          onClick={() => setMode("structured")}
          className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
            mode === "structured"
              ? "bg-primary text-primary-foreground"
              : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
          }`}
        >
          Structured Form
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {mode === "nl" ? (
        <NaturalLanguageInput onSubmit={handleNLSubmit} loading={loading} />
      ) : (
        <StructuredTripForm
          onSubmit={handleStructuredSubmit}
          loading={loading}
        />
      )}

      {/* Show parsed trip result */}
      {currentTrip && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold">
                {currentTrip.title || "Your Trip"}
              </h3>
              <p className="text-sm text-muted-foreground">
                Status: {currentTrip.status}
              </p>
            </div>
            <Button
              onClick={() =>
                navigate(`/trips/${currentTrip.id}/search`)
              }
            >
              Search Flights
            </Button>
          </div>

          {currentTrip.parsed_input?.interpretation_notes && (
            <p className="text-sm text-muted-foreground italic">
              {String(currentTrip.parsed_input.interpretation_notes)}
            </p>
          )}

          <LegList legs={currentTrip.legs} />
        </div>
      )}
    </div>
  );
}
