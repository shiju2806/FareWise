import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { GroupTripDetail as GroupTripDetailType } from "@/types/collaboration";

interface Props {
  detail: GroupTripDetailType;
}

const statusColors: Record<string, string> = {
  accepted: "text-green-600",
  invited: "text-amber-600",
  declined: "text-red-600",
};

export function GroupTripDetailView({ detail }: Props) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">{detail.name}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            <span className="text-muted-foreground">Destination:</span>{" "}
            {detail.destination_city}
          </p>
          <p>
            <span className="text-muted-foreground">Dates:</span>{" "}
            {detail.start_date} — {detail.end_date}
          </p>
          <p>
            <span className="text-muted-foreground">Organizer:</span>{" "}
            {detail.organizer}
          </p>
          {detail.notes && (
            <p className="text-muted-foreground italic">{detail.notes}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">
            Members ({detail.members.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {detail.members.map((m) => (
              <div
                key={m.id}
                className="flex items-center justify-between py-1.5 border-b last:border-0"
              >
                <div>
                  <p className="text-sm font-medium">
                    {m.name}
                    {m.role === "organizer" && (
                      <span className="ml-1 text-xs text-muted-foreground">
                        (organizer)
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {m.email}
                    {m.department ? ` · ${m.department}` : ""}
                  </p>
                </div>
                <span
                  className={`text-xs font-medium capitalize ${
                    statusColors[m.status] || ""
                  }`}
                >
                  {m.status}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {detail.coordination_tips.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Coordination Tips</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1.5 text-sm">
              {detail.coordination_tips.map((tip, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-primary flex-shrink-0">*</span>
                  <span>{tip}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
