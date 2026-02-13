import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BadgeDetail } from "@/types/analytics";

interface Props {
  badges: BadgeDetail[];
  allBadges: BadgeDetail[];
}

const BADGE_EMOJI: Record<string, string> = {
  "bird": "\uD83D\uDC26",
  "piggy-bank": "\uD83D\uDC37",
  "plane": "\u2708\uFE0F",
  "shield-check": "\uD83D\uDEE1\uFE0F",
  "sliders-horizontal": "\uD83C\uDFDA\uFE0F",
  "flag": "\uD83C\uDFC1",
  "users": "\uD83D\uDC65",
  "eye": "\uD83D\uDC41\uFE0F",
  "globe": "\uD83C\uDF0D",
  "calendar-check": "\uD83D\uDCC5",
  "trending-down": "\uD83D\uDCC9",
  "flame": "\uD83D\uDD25",
};

export function BadgeCollection({ badges, allBadges }: Props) {
  const earnedIds = new Set(badges.map((b) => b.id));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          Badges ({badges.length}/{allBadges.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
          {allBadges.map((badge) => {
            const earned = earnedIds.has(badge.id);
            return (
              <div
                key={badge.id}
                className={`text-center p-3 rounded-lg border transition-colors ${
                  earned
                    ? "border-primary bg-primary/5"
                    : "border-border opacity-40 grayscale"
                }`}
                title={badge.desc}
              >
                <div className="text-2xl mb-1">
                  {BADGE_EMOJI[badge.icon] || "\uD83C\uDFC6"}
                </div>
                <p className="text-xs font-medium leading-tight">{badge.name}</p>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
