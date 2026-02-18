import { Card, CardContent } from "@/components/ui/card";
import type { SavingsGoal } from "@/types/analytics";
import { formatPrice } from "@/lib/currency";

interface Props {
  goal: SavingsGoal;
}

export function CompanySavingsGoal({ goal }: Props) {
  const pct = goal.progress_pct;
  const barColor =
    pct >= 100
      ? "bg-emerald-500"
      : pct >= 50
      ? "bg-green-500"
      : pct >= 25
      ? "bg-amber-500"
      : "bg-red-400";

  return (
    <Card>
      <CardContent className="pt-5 pb-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold">
            {goal.quarter} Company Savings Goal
          </h3>
          <span className="text-xs text-muted-foreground">
            {goal.trip_count} trip{goal.trip_count !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Progress bar */}
        <div className="h-3 bg-muted rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${barColor}`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>

        <div className="flex items-center justify-between mt-1.5">
          <span className="text-sm font-bold">
            {formatPrice(goal.total_savings)}
          </span>
          <span className="text-xs text-muted-foreground">
            {pct >= 100
              ? "Goal reached!"
              : `${formatPrice(goal.target - goal.total_savings)} to go`}
          </span>
          <span className="text-sm text-muted-foreground">
            {formatPrice(goal.target)}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
