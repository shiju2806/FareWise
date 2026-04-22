import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import apiClient from "@/api/client";
import type { TripLeg } from "@/types/trip";

interface Props {
  tripId: string;
  leg: TripLeg;
  onAdded: () => void | Promise<void>;
}

export function AddReturnFlightForm({ tripId, leg, onAdded }: Props) {
  const [showForm, setShowForm] = useState(false);
  const [returnDate, setReturnDate] = useState("");
  const [adding, setAdding] = useState(false);

  async function handleAdd() {
    if (!returnDate) return;
    setAdding(true);
    try {
      await apiClient.post(`/trips/${tripId}/add-leg`, {
        origin_city: leg.destination_city,
        destination_city: leg.origin_city,
        preferred_date: returnDate,
        flexibility_days: leg.flexibility_days,
        cabin_class: leg.cabin_class,
        passengers: leg.passengers,
      });
      await onAdded();
      setShowForm(false);
      setReturnDate("");
    } catch {
      // Silently handle
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="rounded-md border border-border p-3">
      {!showForm ? (
        <button
          type="button"
          onClick={() => setShowForm(true)}
          className="text-sm text-primary hover:underline font-medium"
        >
          + Add return flight ({leg.destination_city} &rarr; {leg.origin_city})
        </button>
      ) : (
        <div className="flex items-end gap-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              Return: {leg.destination_city} &rarr; {leg.origin_city}
            </label>
            <Input
              type="date"
              value={returnDate}
              min={leg.preferred_date || undefined}
              onChange={(e) => setReturnDate(e.target.value)}
            />
          </div>
          <Button size="sm" disabled={!returnDate || adding} onClick={handleAdd}>
            {adding ? "Adding..." : "Add Return"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => { setShowForm(false); setReturnDate(""); }}
          >
            Cancel
          </Button>
        </div>
      )}
    </div>
  );
}
