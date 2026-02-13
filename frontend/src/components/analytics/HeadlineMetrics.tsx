import { Card, CardContent } from "@/components/ui/card";
import type { HeadlineMetrics as HeadlineMetricsType } from "@/types/analytics";

interface Props {
  metrics: HeadlineMetricsType;
}

export function HeadlineMetrics({ metrics }: Props) {
  const cards = [
    {
      label: "Total Trips",
      value: metrics.total_trips.toLocaleString(),
      sub: "approved",
    },
    {
      label: "Total Spend",
      value: `$${metrics.total_spend.toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
      sub: "CAD",
    },
    {
      label: "Total Savings",
      value: `$${metrics.total_savings.toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
      sub: "vs. most expensive",
    },
    {
      label: "Active Users",
      value: metrics.active_users.toString(),
      sub: "last 30 days",
    },
    {
      label: "Compliance",
      value: `${(metrics.compliance_rate * 100).toFixed(1)}%`,
      sub: "policy adherence",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {cards.map((c) => (
        <Card key={c.label}>
          <CardContent className="pt-4 pb-3 px-4">
            <p className="text-xs text-muted-foreground">{c.label}</p>
            <p className="text-2xl font-bold mt-1">{c.value}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{c.sub}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
