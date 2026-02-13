import { useState } from "react";
import { Button } from "@/components/ui/button";
import { BundleCard } from "./BundleCard";
import { BundleDateMatrix } from "./BundleDateMatrix";
import type { BundleResult } from "@/types/bundle";
import apiClient from "@/api/client";

interface Props {
  legId: string;
  destination: string;
}

export function BundleOptimizer({ legId, destination }: Props) {
  const [result, setResult] = useState<BundleResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nights, setNights] = useState(3);
  const [showMatrix, setShowMatrix] = useState(false);

  async function handleOptimize() {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.post(`/search/${legId}/bundle`, {
        hotel_nights: nights,
      });
      setResult(res.data as BundleResult);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Bundle optimization failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4 rounded-lg border border-border p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          Bundle Optimizer — {destination}
        </h3>
      </div>

      <p className="text-xs text-muted-foreground">
        Find the best flight + hotel combination across flexible dates.
      </p>

      <div className="flex items-end gap-3">
        <div>
          <label className="text-xs text-muted-foreground block mb-1">
            Hotel nights
          </label>
          <input
            type="number"
            min={1}
            max={14}
            value={nights}
            onChange={(e) => setNights(Number(e.target.value))}
            className="w-16 px-2 py-1.5 rounded-md border border-input text-sm bg-background"
          />
        </div>
        <Button onClick={handleOptimize} disabled={loading} size="sm">
          {loading ? "Optimizing..." : "Find Best Bundles"}
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-32 bg-muted animate-pulse rounded-lg" />
          ))}
        </div>
      )}

      {result && !loading && (
        <div className="space-y-5">
          {/* Top bundles */}
          {result.bundles.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {result.bundles.map((b) => (
                <BundleCard key={b.departure_date} bundle={b} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No bundle combinations found.
            </p>
          )}

          {/* Date matrix toggle */}
          {result.date_matrix.length > 0 && (
            <div>
              <button
                type="button"
                onClick={() => setShowMatrix(!showMatrix)}
                className="text-xs text-primary hover:underline"
              >
                {showMatrix ? "Hide date matrix" : "Show all date combinations"}
              </button>
              {showMatrix && (
                <div className="mt-3">
                  <BundleDateMatrix matrix={result.date_matrix} />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
