import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import type { LegInput } from "@/stores/tripStore";

interface Props {
  onSubmit: (legs: LegInput[]) => Promise<void>;
  loading: boolean;
  initialLegs?: LegInput[];
}

const EMPTY_LEG: LegInput = {
  origin_city: "",
  destination_city: "",
  preferred_date: "",
  flexibility_days: 3,
  cabin_class: "economy",
  passengers: 1,
};

export function StructuredTripForm({ onSubmit, loading, initialLegs }: Props) {
  const [legs, setLegs] = useState<LegInput[]>(
    initialLegs && initialLegs.length > 0 ? initialLegs : [{ ...EMPTY_LEG }]
  );
  const [roundTrip, setRoundTrip] = useState(false);

  function updateLeg(index: number, field: keyof LegInput, value: string | number) {
    setLegs((prev) =>
      prev.map((leg, i) => (i === index ? { ...leg, [field]: value } : leg))
    );
  }

  function addLeg() {
    const lastLeg = legs[legs.length - 1];
    setLegs((prev) => [
      ...prev,
      {
        ...EMPTY_LEG,
        origin_city: lastLeg?.destination_city || "",
      },
    ]);
  }

  function removeLeg(index: number) {
    if (legs.length <= 1) return;
    setLegs((prev) => prev.filter((_, i) => i !== index));
  }

  const [returnDate, setReturnDate] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const valid = legs.every(
      (l) => l.origin_city.trim() && l.destination_city.trim() && l.preferred_date
    );
    if (!valid) return;
    if (roundTrip && !returnDate) return;

    const allLegs = [...legs];
    if (roundTrip && legs.length === 1) {
      allLegs.push({
        ...EMPTY_LEG,
        origin_city: legs[0].destination_city,
        destination_city: legs[0].origin_city,
        preferred_date: returnDate,
        flexibility_days: legs[0].flexibility_days,
        cabin_class: legs[0].cabin_class,
        passengers: legs[0].passengers,
      });
    }
    await onSubmit(allLegs);
  }

  const allValid = legs.every(
    (l) => l.origin_city.trim() && l.destination_city.trim() && l.preferred_date
  ) && (!roundTrip || returnDate);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Build your itinerary</CardTitle>
        <CardDescription>
          Add legs manually. The destination of each leg auto-fills as the
          origin of the next.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          {legs.map((leg, i) => (
            <div
              key={i}
              className="space-y-3 rounded-lg border border-border p-4 relative"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Leg {i + 1}</span>
                {legs.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeLeg(i)}
                    className="text-xs text-muted-foreground hover:text-destructive transition-colors"
                  >
                    Remove
                  </button>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">
                    From
                  </label>
                  <Input
                    placeholder="e.g. Toronto"
                    value={leg.origin_city}
                    onChange={(e) => updateLeg(i, "origin_city", e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">
                    To
                  </label>
                  <Input
                    placeholder="e.g. New York"
                    value={leg.destination_city}
                    onChange={(e) =>
                      updateLeg(i, "destination_city", e.target.value)
                    }
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-4 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">
                    Date
                  </label>
                  <Input
                    type="date"
                    value={leg.preferred_date}
                    onChange={(e) =>
                      updateLeg(i, "preferred_date", e.target.value)
                    }
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">
                    Flexibility
                  </label>
                  <select
                    value={leg.flexibility_days}
                    onChange={(e) =>
                      updateLeg(i, "flexibility_days", Number(e.target.value))
                    }
                    className="h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
                  >
                    <option value={0}>Exact date</option>
                    <option value={1}>&plusmn;1 day</option>
                    <option value={3}>&plusmn;3 days</option>
                    <option value={7}>&plusmn;7 days</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">
                    Cabin
                  </label>
                  <select
                    value={leg.cabin_class}
                    onChange={(e) => updateLeg(i, "cabin_class", e.target.value)}
                    className="h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
                  >
                    <option value="economy">Economy</option>
                    <option value="premium_economy">Premium Economy</option>
                    <option value="business">Business</option>
                    <option value="first">First</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground">
                    Passengers
                  </label>
                  <Input
                    type="number"
                    min={1}
                    max={9}
                    value={leg.passengers}
                    onChange={(e) =>
                      updateLeg(i, "passengers", Number(e.target.value))
                    }
                  />
                </div>
              </div>
            </div>
          ))}

          {/* Round trip toggle — only for single-leg trips */}
          {legs.length === 1 && (
            <div className="space-y-3 rounded-lg border border-border p-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={roundTrip}
                  onChange={(e) => {
                    setRoundTrip(e.target.checked);
                    if (!e.target.checked) setReturnDate("");
                  }}
                  className="h-4 w-4 rounded border-input"
                />
                <span className="text-sm font-medium">Round trip</span>
              </label>
              {roundTrip && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-muted-foreground">
                      Return date
                    </label>
                    <Input
                      type="date"
                      value={returnDate}
                      min={legs[0].preferred_date || undefined}
                      onChange={(e) => setReturnDate(e.target.value)}
                      required
                    />
                  </div>
                  <div className="flex items-end">
                    <p className="text-xs text-muted-foreground pb-2">
                      {legs[0].destination_city || "Destination"} &rarr;{" "}
                      {legs[0].origin_city || "Origin"}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="flex items-center gap-3">
            {!roundTrip && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={addLeg}
              >
                + Add leg
              </Button>
            )}
            <div className="flex-1" />
            <Button type="submit" disabled={loading || !allValid}>
              {loading ? "Creating..." : "Create Trip"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
