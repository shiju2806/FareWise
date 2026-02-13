import { Slider } from "@/components/ui/slider";
import { useDebounce } from "@/hooks/useDebounce";
import { useEffect, useState } from "react";

interface Props {
  value: number;
  onChange: (value: number) => void;
  loading?: boolean;
}

export function WhatIfSlider({ value, onChange, loading }: Props) {
  const [local, setLocal] = useState(value);
  const debounced = useDebounce(local, 300);

  useEffect(() => {
    if (debounced !== value) {
      onChange(debounced);
    }
  }, [debounced, onChange, value]);

  useEffect(() => {
    setLocal(value);
  }, [value]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">What If?</h3>
        {loading && (
          <span className="text-xs text-muted-foreground animate-pulse">
            Rescoring...
          </span>
        )}
      </div>
      <div className="flex items-center gap-4">
        <span className="text-xs text-muted-foreground w-16 text-right shrink-0">
          Cheapest
        </span>
        <Slider
          value={[local]}
          onValueChange={([v]) => setLocal(v)}
          min={0}
          max={100}
          step={1}
          className="flex-1"
        />
        <span className="text-xs text-muted-foreground w-20 shrink-0">
          Convenient
        </span>
      </div>
      <div className="text-center text-xs text-muted-foreground">
        {local <= 25
          ? "Prioritizing lowest price"
          : local <= 50
            ? "Balancing cost and convenience"
            : local <= 75
              ? "Prioritizing shorter flights"
              : "Prioritizing convenience"}
      </div>
    </div>
  );
}
