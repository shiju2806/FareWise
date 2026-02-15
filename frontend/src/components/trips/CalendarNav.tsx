const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

interface Props {
  year: number;
  month: number; // 0-indexed (0 = January)
  onChange: (year: number, month: number) => void;
}

export function CalendarNav({ year, month, onChange }: Props) {
  function prev() {
    if (month === 0) onChange(year - 1, 11);
    else onChange(year, month - 1);
  }

  function next() {
    if (month === 11) onChange(year + 1, 0);
    else onChange(year, month + 1);
  }

  function goToday() {
    const now = new Date();
    onChange(now.getFullYear(), now.getMonth());
  }

  const isCurrentMonth =
    year === new Date().getFullYear() && month === new Date().getMonth();

  return (
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={prev}
          className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Previous month"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h3 className="text-sm font-semibold min-w-[140px] text-center">
          {MONTH_NAMES[month]} {year}
        </h3>
        <button
          type="button"
          onClick={next}
          className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Next month"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>

      {!isCurrentMonth && (
        <button
          type="button"
          onClick={goToday}
          className="text-xs text-primary hover:underline"
        >
          Today
        </button>
      )}
    </div>
  );
}
