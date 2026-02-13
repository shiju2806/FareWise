import type { EventWarning } from "@/types/hotel";

interface Props {
  warnings: EventWarning[];
}

export function HotelEventWarning({ warnings }: Props) {
  if (warnings.length === 0) return null;

  return (
    <div className="space-y-2">
      {warnings.map((w, i) => (
        <div
          key={i}
          className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 flex items-start gap-2"
        >
          <span className="text-base mt-0.5">{"\u26A0\uFE0F"}</span>
          <div>
            <p className="font-medium">{w.title}</p>
            <p className="text-xs mt-0.5">{w.message}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
