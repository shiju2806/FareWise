import type { DateEvent } from "@/types/event";

const impactColors: Record<string, string> = {
  low: "bg-gray-100 text-gray-600 border-gray-200",
  medium: "bg-amber-100 text-amber-700 border-amber-200",
  high: "bg-orange-100 text-orange-700 border-orange-200",
  very_high: "bg-red-100 text-red-700 border-red-200",
};

const categoryIcons: Record<string, string> = {
  briefcase: "\uD83D\uDCBC",
  trophy: "\uD83C\uDFC6",
  music: "\uD83C\uDFB5",
  theater: "\uD83C\uDFAD",
  users: "\uD83D\uDC65",
  flag: "\uD83C\uDFF3\uFE0F",
  calendar: "\uD83D\uDCC5",
};

interface Props {
  events: DateEvent[];
  compact?: boolean;
}

export function EventBadge({ events, compact }: Props) {
  if (events.length === 0) return null;

  // Show the highest impact event
  const sorted = [...events].sort((a, b) => {
    const order = { very_high: 4, high: 3, medium: 2, low: 1 };
    return (order[b.impact_level] || 0) - (order[a.impact_level] || 0);
  });

  const top = sorted[0];
  const color = impactColors[top.impact_level] || impactColors.low;
  const icon = categoryIcons[top.icon] || categoryIcons.calendar;

  if (compact) {
    return (
      <span
        className={`inline-flex items-center gap-0.5 px-1 py-0.5 rounded text-[8px] font-medium border ${color}`}
        title={top.title}
      >
        <span>{icon}</span>
        {events.length > 1 && <span>+{events.length - 1}</span>}
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium border ${color}`}
      title={top.title}
    >
      <span>{icon}</span>
      <span className="truncate max-w-[60px]">{top.title}</span>
      {events.length > 1 && (
        <span className="opacity-70">+{events.length - 1}</span>
      )}
    </span>
  );
}
