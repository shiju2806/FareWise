import { useEffect } from "react";
import { useAnalyticsStore } from "@/stores/analyticsStore";
import { HeadlineMetrics } from "@/components/analytics/HeadlineMetrics";
import { SpendSavingsChart } from "@/components/analytics/SpendSavingsChart";
import { ComplianceTrend } from "@/components/analytics/ComplianceTrend";
import { DepartmentBreakdown } from "@/components/analytics/DepartmentBreakdown";
import { CSVExportButton } from "@/components/analytics/CSVExportButton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AnalyticsDashboard() {
  const { overview, savingsSummary, loading, fetchOverview, fetchSavingsSummary } =
    useAnalyticsStore();

  useEffect(() => {
    fetchOverview();
    fetchSavingsSummary();
  }, [fetchOverview, fetchSavingsSummary]);

  if (loading && !overview) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-64 bg-muted animate-pulse rounded" />
        <div className="grid grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-24 bg-muted animate-pulse rounded-lg" />
          ))}
        </div>
        <div className="h-72 bg-muted animate-pulse rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Analytics</h2>
          <p className="text-muted-foreground mt-1">
            Company-wide travel spend, savings, and compliance.
          </p>
        </div>
        <CSVExportButton />
      </div>

      {overview && <HeadlineMetrics metrics={overview.headline} />}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {overview && overview.spend_trend.length > 0 && (
          <SpendSavingsChart data={overview.spend_trend} />
        )}
        {overview && overview.spend_trend.length > 0 && (
          <ComplianceTrend data={overview.spend_trend} />
        )}
      </div>

      {/* Department breakdown from latest monthly snapshot */}
      {overview?.latest_snapshot && "trip_counts" in overview.latest_snapshot && (
        <DepartmentBreakdown
          departments={
            ((overview.latest_snapshot as Record<string, unknown>)
              ?.departments as Record<string, { trips: number; spend: number }>) || {}
          }
        />
      )}

      {/* Savings Summary */}
      {savingsSummary && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Savings Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Reports</p>
                <p className="text-xl font-bold">{savingsSummary.total_reports}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Selected</p>
                <p className="text-xl font-bold">
                  ${savingsSummary.total_selected.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Savings</p>
                <p className="text-xl font-bold text-green-600">
                  ${savingsSummary.total_savings.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Avg Savings/Trip</p>
                <p className="text-xl font-bold">
                  ${savingsSummary.avg_savings.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Cheapest</p>
                <p className="text-xl font-bold">
                  ${savingsSummary.total_cheapest.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Most Expensive</p>
                <p className="text-xl font-bold">
                  ${savingsSummary.total_most_expensive.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
