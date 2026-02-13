import { useEffect } from "react";
import { useAnalyticsStore } from "@/stores/analyticsStore";
import { useAuthStore } from "@/stores/authStore";
import { Leaderboard } from "@/components/gamification/Leaderboard";

export default function LeaderboardPage() {
  const { leaderboard, loading, fetchLeaderboard } = useAnalyticsStore();
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    fetchLeaderboard();
  }, [fetchLeaderboard]);

  if (loading && !leaderboard) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="h-96 bg-muted animate-pulse rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Leaderboard</h2>
        <p className="text-muted-foreground mt-1">
          {leaderboard?.period
            ? `Rankings for ${leaderboard.period}`
            : "Company-wide traveler rankings"}
        </p>
      </div>

      {leaderboard && leaderboard.entries.length > 0 ? (
        <Leaderboard
          entries={leaderboard.entries}
          currentUserId={user?.id}
        />
      ) : (
        <div className="text-center py-12">
          <p className="text-lg font-medium">No rankings yet</p>
          <p className="text-sm text-muted-foreground mt-1">
            Rankings are computed daily. Check back tomorrow!
          </p>
        </div>
      )}
    </div>
  );
}
