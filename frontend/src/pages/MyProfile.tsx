import { useEffect } from "react";
import { useAnalyticsStore } from "@/stores/analyticsStore";
import { useAuthStore } from "@/stores/authStore";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScoreCard } from "@/components/gamification/ScoreCard";
import { BadgeCollection } from "@/components/gamification/BadgeCollection";
import { SavingsHistory } from "@/components/gamification/SavingsHistory";
import { Leaderboard } from "@/components/gamification/Leaderboard";
import { TravelPreferencesForm } from "@/components/profile/TravelPreferencesForm";

export default function MyProfile() {
  const { myStats, leaderboard, loading, fetchMyStats, fetchLeaderboard } =
    useAnalyticsStore();
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    fetchMyStats();
    fetchLeaderboard();
  }, [fetchMyStats, fetchLeaderboard]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">My Profile</h2>
        <p className="text-muted-foreground mt-1">
          Your stats, rankings, and travel preferences.
        </p>
      </div>

      <Tabs defaultValue="stats">
        <TabsList>
          <TabsTrigger value="stats">My Stats</TabsTrigger>
          <TabsTrigger value="leaderboard">Leaderboard</TabsTrigger>
          <TabsTrigger value="preferences">Preferences</TabsTrigger>
        </TabsList>

        <TabsContent value="stats">
          {loading && !myStats ? (
            <div className="space-y-4 pt-4">
              <div className="h-36 bg-muted animate-pulse rounded-lg" />
              <div className="h-48 bg-muted animate-pulse rounded-lg" />
            </div>
          ) : !myStats ? (
            <div className="text-center py-12">
              <p className="text-lg font-medium">No stats yet</p>
              <p className="text-sm text-muted-foreground mt-1">
                Complete some trips to start earning points and badges!
              </p>
            </div>
          ) : (
            <div className="space-y-6 pt-4">
              <ScoreCard
                score={myStats.current.score}
                tier={myStats.current.tier || "bronze"}
                streak={myStats.current.streak || 0}
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
          )}
        </TabsContent>

        <TabsContent value="leaderboard">
          {loading && !leaderboard ? (
            <div className="space-y-4 pt-4">
              <div className="h-96 bg-muted animate-pulse rounded-lg" />
            </div>
          ) : leaderboard && leaderboard.entries.length > 0 ? (
            <div className="pt-4">
              {leaderboard.period && (
                <p className="text-sm text-muted-foreground mb-3">
                  Rankings for {leaderboard.period}
                </p>
              )}
              <Leaderboard
                entries={leaderboard.entries}
                currentUserId={user?.id}
              />
            </div>
          ) : (
            <div className="text-center py-12">
              <p className="text-lg font-medium">No rankings yet</p>
              <p className="text-sm text-muted-foreground mt-1">
                Rankings are computed daily. Check back tomorrow!
              </p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="preferences">
          <TravelPreferencesForm />
        </TabsContent>
      </Tabs>
    </div>
  );
}
