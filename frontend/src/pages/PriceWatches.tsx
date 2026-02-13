import { useEffect, useState } from "react";
import { usePriceWatchStore } from "@/stores/priceWatchStore";
import { PriceWatchCard } from "@/components/pricewatch/PriceWatchCard";
import { PriceWatchSetup } from "@/components/pricewatch/PriceWatchSetup";
import { Button } from "@/components/ui/button";

export default function PriceWatches() {
  const { watches, loadingWatches, fetchWatches } = usePriceWatchStore();
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    fetchWatches();
  }, [fetchWatches]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Price Watches</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Track flight prices and get notified when they drop.
          </p>
        </div>
        <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? "Cancel" : "+ New Watch"}
        </Button>
      </div>

      {showCreate && (
        <PriceWatchSetup
          onCreated={() => setShowCreate(false)}
        />
      )}

      {loadingWatches ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-28 bg-muted animate-pulse rounded-lg"
            />
          ))}
        </div>
      ) : watches.length === 0 ? (
        <div className="text-center py-12 space-y-3">
          <p className="text-muted-foreground">No active price watches.</p>
          {!showCreate && (
            <Button variant="outline" onClick={() => setShowCreate(true)}>
              Create your first watch
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {watches.map((watch) => (
            <PriceWatchCard key={watch.id} watch={watch} />
          ))}
        </div>
      )}
    </div>
  );
}
