import { Input } from "@/components/ui/input";
import type { TripLeg } from "@/types/trip";

interface Props {
  leg: TripLeg;
  companionsCount: number;
  companionsSameDates: boolean | null;
  onPatch: (legId: string, updates: Partial<TripLeg>) => void;
}

export function CompanionDatePicker({ leg, companionsCount, companionsSameDates, onPatch }: Props) {
  return (
    <div className="rounded-md border border-violet-200 bg-violet-50/50 p-3 space-y-2">
      <h4 className="text-sm font-semibold text-violet-700">
        Companion Travel ({companionsCount} companion{companionsCount > 1 ? "s" : ""})
      </h4>
      {companionsSameDates === false ? (
        <div className="flex items-center gap-3">
          <span className="text-sm text-violet-600">Companion date:</span>
          <Input
            type="date"
            className="w-40 h-8 text-sm"
            value={leg.companion_preferred_date || leg.preferred_date}
            onChange={(e) => {
              if (e.target.value) {
                onPatch(leg.id, { companion_preferred_date: e.target.value });
              }
            }}
          />
          {leg.companion_preferred_date && (
            <button
              type="button"
              className="text-xs text-violet-500 underline"
              onClick={() => onPatch(leg.id, { companion_preferred_date: null as unknown as string })}
            >
              Reset to employee date
            </button>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name={`companion-date-${leg.id}`}
              checked={!leg.companion_preferred_date}
              onChange={() => {
                onPatch(leg.id, { companion_preferred_date: null as unknown as string });
              }}
            />
            Same as employee ({leg.preferred_date})
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name={`companion-date-${leg.id}`}
              checked={!!leg.companion_preferred_date}
              onChange={() => {
                onPatch(leg.id, { companion_preferred_date: leg.preferred_date });
              }}
            />
            Different date
          </label>
          {leg.companion_preferred_date && (
            <Input
              type="date"
              className="w-40 h-8 text-sm"
              value={leg.companion_preferred_date}
              onChange={(e) => {
                if (e.target.value) {
                  onPatch(leg.id, { companion_preferred_date: e.target.value });
                }
              }}
            />
          )}
        </div>
      )}
      <p className="text-[10px] text-violet-600">
        Companion pricing will be recalculated based on this date.
      </p>
    </div>
  );
}
