import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  departments: Record<string, { trips: number; spend: number }>;
}

export function DepartmentBreakdown({ departments }: Props) {
  const data = Object.entries(departments).map(([dept, stats]) => ({
    department: dept,
    spend: Math.round(stats.spend),
    trips: stats.trips,
  }));

  if (data.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Department Spend</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis
                type="number"
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
              />
              <YAxis dataKey="department" type="category" tick={{ fontSize: 11 }} width={90} />
              <Tooltip
                formatter={(value: number) => [`$${value.toLocaleString()}`, "Spend"]}
              />
              <Bar dataKey="spend" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
