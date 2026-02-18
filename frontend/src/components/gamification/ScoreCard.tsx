import { Card, CardContent } from "@/components/ui/card";

const tierColors: Record<string, string> = {
  bronze: "bg-amber-100 text-amber-800",
  silver: "bg-gray-100 text-gray-700",
  gold: "bg-yellow-100 text-yellow-800",
  platinum: "bg-purple-100 text-purple-800",
};

interface Props {
  score: number;
  tier: string;
  streak: number;
  rankDepartment: number | null;
  rankCompany: number | null;
  totalTrips: number;
  totalSavings: number;
  complianceRate: number;
}

export function ScoreCard({
  score,
  tier,
  streak,
  rankDepartment,
  rankCompany,
  totalTrips,
  totalSavings,
  complianceRate,
}: Props) {
  // Score color
  const scoreColor =
    score >= 700
      ? "text-green-600"
      : score >= 400
      ? "text-amber-600"
      : "text-red-600";

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center gap-6">
          {/* Score circle */}
          <div className="relative w-28 h-28 flex-shrink-0">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
              <circle
                cx="50"
                cy="50"
                r="42"
                fill="none"
                stroke="currentColor"
                className="text-muted"
                strokeWidth="8"
              />
              <circle
                cx="50"
                cy="50"
                r="42"
                fill="none"
                stroke="currentColor"
                className={scoreColor}
                strokeWidth="8"
                strokeDasharray={`${(score / 1000) * 264} 264`}
                strokeLinecap="round"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className={`text-2xl font-bold ${scoreColor}`}>{score}</span>
              <span className="text-[10px] text-muted-foreground">/ 1000</span>
            </div>
          </div>

          {/* Stats grid */}
          <div className="flex-1 space-y-3">
            {/* Tier + streak row */}
            <div className="flex items-center gap-2">
              <span
                className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                  tierColors[tier] || tierColors.bronze
                }`}
              >
                {tier.charAt(0).toUpperCase() + tier.slice(1)}
              </span>
              {streak > 0 && (
                <span className="text-xs text-amber-600 font-medium">
                  {streak} compliant trip{streak > 1 ? "s" : ""} in a row
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs text-muted-foreground">Dept Rank</p>
                <p className="text-lg font-bold">
                  {rankDepartment ? `#${rankDepartment}` : "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Company Rank</p>
                <p className="text-lg font-bold">
                  {rankCompany ? `#${rankCompany}` : "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Trips</p>
                <p className="text-lg font-bold">{totalTrips}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Savings</p>
                <p className="text-lg font-bold text-green-600">
                  ${totalSavings.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </p>
              </div>
              <div className="col-span-2">
                <p className="text-xs text-muted-foreground">Compliance</p>
                <div className="flex items-center gap-2 mt-1">
                  <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-green-500 rounded-full"
                      style={{ width: `${complianceRate * 100}%` }}
                    />
                  </div>
                  <span className="text-sm font-medium">
                    {(complianceRate * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
