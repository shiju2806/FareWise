import { useEffect } from "react";
import { useAnalyticsStore } from "@/stores/analyticsStore";
import { ScoreCard } from "@/components/gamification/ScoreCard";
import { BadgeCollection } from "@/components/gamification/BadgeCollection";
import { SavingsHistory } from "@/components/gamification/SavingsHistory";

export default function MyStats() {
  const { myStats, loading, fetchMyStats } = useAnalyticsStore();

  useEffect(() => {
    fetchMyStats();
  }, [fetchMyStats]);

  if (loading && !myStats) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="h-36 bg-muted animate-pulse rounded-lg" />
        <div className="h-48 bg-muted animate-pulse rounded-lg" />
      </div>
    );
  }

  if (!myStats) {
    return (
      <div className="text-center py-12">
        <p className="text-lg font-medium">No stats yet</p>
        <p className="text-sm text-muted-foreground mt-1">
          Complete some trips to start earning points and badges!
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">My Stats</h2>
        <p className="text-muted-foreground mt-1">
          Your traveler score, badges, and savings history.
        </p>
      </div>

      <ScoreCard
        score={myStats.current.score}
        rankDepartment={myStats.current.rank_department}
        rankCompany={myStats.current.rank_company}
        totalTrips={myStats.current.total_trips}
        totalSavings={myStats.current.total_savings}
        complianceRate={myStats.current.compliance_rate}
      />

      <BadgeCollection
        badges={myStats.badges}
        allBadges={myStats.all_badges}
      />

      <SavingsHistory history={myStats.history} />
    </div>
  );
}
