import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SpendTrendPoint } from "@/types/analytics";

interface Props {
  data: SpendTrendPoint[];
}

export function SpendSavingsChart({ data }: Props) {
  const formatted = data.map((d) => ({
    ...d,
    week: new Date(d.period_start).toLocaleDateString("en-CA", {
      month: "short",
      day: "numeric",
    }),
    spend: Math.round(d.spend),
  }));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Weekly Spend Trend</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={formatted}>
              <defs>
                <linearGradient id="spendGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis dataKey="week" tick={{ fontSize: 11 }} />
              <YAxis
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
              />
              <Tooltip
                formatter={(value: number | undefined) => [`$${(value ?? 0).toLocaleString()}`, "Spend"]}
                labelFormatter={(label) => `Week of ${label}`}
              />
              <Area
                type="monotone"
                dataKey="spend"
                stroke="hsl(var(--primary))"
                fill="url(#spendGrad)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
