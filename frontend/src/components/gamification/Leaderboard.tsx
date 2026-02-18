import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { LeaderboardEntry } from "@/types/analytics";

const tierColors: Record<string, string> = {
  bronze: "text-amber-700",
  silver: "text-gray-600",
  gold: "text-yellow-700",
  platinum: "text-purple-700",
};

interface Props {
  entries: LeaderboardEntry[];
  currentUserId?: string;
}

export function Leaderboard({ entries, currentUserId }: Props) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Leaderboard</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-1">
          <div className="grid grid-cols-[2rem_1fr_4.5rem_4rem_4rem_4rem] gap-2 text-xs text-muted-foreground font-medium pb-2 border-b">
            <span>#</span>
            <span>Name</span>
            <span className="text-right">Tier</span>
            <span className="text-right">Score</span>
            <span className="text-right">Trips</span>
            <span className="text-right">Saved</span>
          </div>
          {entries.map((e, i) => {
            const isMe = e.user_id === currentUserId;
            return (
              <div
                key={e.user_id}
                className={`grid grid-cols-[2rem_1fr_4.5rem_4rem_4rem_4rem] gap-2 items-center py-1.5 text-sm ${
                  isMe ? "bg-primary/5 -mx-2 px-2 rounded" : ""
                }`}
              >
                <span className="font-medium text-muted-foreground">
                  {i === 0 ? "\uD83E\uDD47" : i === 1 ? "\uD83E\uDD48" : i === 2 ? "\uD83E\uDD49" : `${i + 1}`}
                </span>
                <div className="min-w-0">
                  <p className={`truncate ${isMe ? "font-semibold" : ""}`}>
                    {e.name}
                    {isMe && " (you)"}
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {e.department}
                  </p>
                </div>
                <span className={`text-right text-[10px] font-semibold capitalize ${tierColors[e.tier] || ""}`}>
                  {e.tier}
                </span>
                <span className="text-right font-bold">{e.score}</span>
                <span className="text-right">{e.trips}</span>
                <span className="text-right text-green-600">
                  ${e.savings.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
