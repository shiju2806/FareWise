import { useState } from "react";
import { Button } from "@/components/ui/button";
import { usePriceWatchStore } from "@/stores/priceWatchStore";

interface Props {
  defaultOrigin?: string;
  defaultDestination?: string;
  defaultDate?: string;
  defaultPrice?: number;
  defaultCabin?: string;
  onCreated?: () => void;
}

export function PriceWatchSetup({
  defaultOrigin = "",
  defaultDestination = "",
  defaultDate = "",
  defaultPrice,
  defaultCabin = "economy",
  onCreated,
}: Props) {
  const { creating, createWatch } = usePriceWatchStore();

  const [origin, setOrigin] = useState(defaultOrigin);
  const [destination, setDestination] = useState(defaultDestination);
  const [targetDate, setTargetDate] = useState(defaultDate);
  const [targetPrice, setTargetPrice] = useState(
    defaultPrice ? Math.round(defaultPrice * 0.85).toString() : ""
  );
  const [cabinClass, setCabinClass] = useState(defaultCabin);
  const [flexibility, setFlexibility] = useState(3);

  const canSubmit = origin && destination && targetDate;

  async function handleSubmit() {
    if (!canSubmit) return;
    await createWatch({
      watch_type: "flight",
      origin: origin.toUpperCase(),
      destination: destination.toUpperCase(),
      target_date: targetDate,
      flexibility_days: flexibility,
      target_price: targetPrice ? parseFloat(targetPrice) : undefined,
      cabin_class: cabinClass,
      current_price: defaultPrice,
    });
    onCreated?.();
  }

  return (
    <div className="rounded-lg border bg-card p-4 space-y-4">
      <h3 className="text-sm font-semibold">Create Price Watch</h3>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-muted-foreground">Origin</label>
          <input
            type="text"
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
            placeholder="JFK"
            className="w-full mt-1 px-2 py-1.5 text-sm border rounded-md bg-background"
            maxLength={3}
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground">Destination</label>
          <input
            type="text"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            placeholder="LAX"
            className="w-full mt-1 px-2 py-1.5 text-sm border rounded-md bg-background"
            maxLength={3}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-muted-foreground">Travel Date</label>
          <input
            type="date"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            className="w-full mt-1 px-2 py-1.5 text-sm border rounded-md bg-background"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground">
            Target Price ($)
          </label>
          <input
            type="number"
            value={targetPrice}
            onChange={(e) => setTargetPrice(e.target.value)}
            placeholder="Auto: -15%"
            className="w-full mt-1 px-2 py-1.5 text-sm border rounded-md bg-background"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-muted-foreground">Cabin Class</label>
          <select
            value={cabinClass}
            onChange={(e) => setCabinClass(e.target.value)}
            className="w-full mt-1 px-2 py-1.5 text-sm border rounded-md bg-background"
          >
            <option value="economy">Economy</option>
            <option value="premium_economy">Premium Economy</option>
            <option value="business">Business</option>
            <option value="first">First</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground">
            Flexibility (days)
          </label>
          <select
            value={flexibility}
            onChange={(e) => setFlexibility(Number(e.target.value))}
            className="w-full mt-1 px-2 py-1.5 text-sm border rounded-md bg-background"
          >
            <option value={0}>Exact date</option>
            <option value={1}>&plusmn;1 day</option>
            <option value={3}>&plusmn;3 days</option>
            <option value={7}>&plusmn;7 days</option>
          </select>
        </div>
      </div>

      <Button
        onClick={handleSubmit}
        disabled={!canSubmit || creating}
        className="w-full"
        size="sm"
      >
        {creating ? "Creating..." : "Start Watching"}
      </Button>
    </div>
  );
}
