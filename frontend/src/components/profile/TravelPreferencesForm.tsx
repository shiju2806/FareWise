import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import apiClient from "@/api/client";

interface Preferences {
  excluded_airlines: string[];
  preferred_cabin: string | null;
  prefer_nonstop: boolean;
  max_stops: number | null;
  max_layover_minutes: number | null;
  seat_preference: string | null;
  preferred_alliances: string[];
  prefer_same_tier: boolean;
}

const CABIN_OPTIONS = [
  { value: "economy", label: "Economy" },
  { value: "premium_economy", label: "Premium Economy" },
  { value: "business", label: "Business" },
  { value: "first", label: "First" },
];

const LAYOVER_OPTIONS = [
  { value: 60, label: "1 hour" },
  { value: 120, label: "2 hours" },
  { value: 180, label: "3 hours" },
  { value: 240, label: "4 hours" },
  { value: 360, label: "6 hours" },
  { value: 480, label: "8 hours" },
];

const SEAT_OPTIONS = [
  { value: "window", label: "Window" },
  { value: "aisle", label: "Aisle" },
  { value: "no_preference", label: "No preference" },
];

const ALLIANCE_OPTIONS = [
  { value: "star_alliance", label: "Star Alliance", airlines: "Air Canada, United, Lufthansa, ANA, Singapore..." },
  { value: "oneworld", label: "oneworld", airlines: "American, British Airways, Qantas, Cathay, JAL..." },
  { value: "skyteam", label: "SkyTeam", airlines: "Delta, Air France, KLM, Korean Air..." },
];

export function TravelPreferencesForm() {
  const [prefs, setPrefs] = useState<Preferences>({
    excluded_airlines: [],
    preferred_cabin: null,
    prefer_nonstop: false,
    max_stops: null,
    max_layover_minutes: null,
    seat_preference: null,
    preferred_alliances: [],
    prefer_same_tier: false,
  });
  const [airlineInput, setAirlineInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient
      .get("/users/me/preferences")
      .then((res) => setPrefs(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    try {
      const res = await apiClient.patch("/users/me/preferences", prefs);
      setPrefs(res.data);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {
      // silent
    } finally {
      setSaving(false);
    }
  }

  function addAirline() {
    const code = airlineInput.trim().toUpperCase();
    if (code && code.length >= 2 && !prefs.excluded_airlines.includes(code)) {
      setPrefs((p) => ({
        ...p,
        excluded_airlines: [...p.excluded_airlines, code],
      }));
    }
    setAirlineInput("");
  }

  function removeAirline(code: string) {
    setPrefs((p) => ({
      ...p,
      excluded_airlines: p.excluded_airlines.filter((a) => a !== code),
    }));
  }

  if (loading) {
    return (
      <div className="space-y-4 pt-4">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="h-64 bg-muted animate-pulse rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6 pt-4">
      <Card>
        <CardContent className="pt-6 space-y-6">
          {/* Excluded Airlines */}
          <div>
            <label className="text-sm font-medium">Excluded Airlines</label>
            <p className="text-xs text-muted-foreground mb-2">
              Airlines you never want to see in search results (IATA codes).
            </p>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {prefs.excluded_airlines.map((code) => (
                <span
                  key={code}
                  className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-xs font-medium"
                >
                  {code}
                  <button
                    type="button"
                    onClick={() => removeAirline(code)}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    &times;
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={airlineInput}
                onChange={(e) => setAirlineInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addAirline())}
                placeholder="e.g. AC, WS"
                maxLength={3}
                className="w-24 rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
              <Button variant="outline" size="sm" onClick={addAirline} type="button">
                Add
              </Button>
            </div>
          </div>

          {/* Preferred Cabin */}
          <div>
            <label className="text-sm font-medium">Preferred Cabin Class</label>
            <p className="text-xs text-muted-foreground mb-2">
              Your default cabin class preference for new trips.
            </p>
            <select
              value={prefs.preferred_cabin || ""}
              onChange={(e) =>
                setPrefs((p) => ({
                  ...p,
                  preferred_cabin: e.target.value || null,
                }))
              }
              className="w-48 rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
            >
              <option value="">No preference</option>
              {CABIN_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Prefer Nonstop */}
          <div className="flex items-center justify-between">
            <div>
              <label className="text-sm font-medium">Prefer Nonstop Flights</label>
              <p className="text-xs text-muted-foreground">
                Boost nonstop flights higher in search results.
              </p>
            </div>
            <Switch
              checked={prefs.prefer_nonstop}
              onCheckedChange={(checked) =>
                setPrefs((p) => ({ ...p, prefer_nonstop: checked }))
              }
            />
          </div>

          {/* Max Stops */}
          <div>
            <label className="text-sm font-medium">Maximum Stops</label>
            <p className="text-xs text-muted-foreground mb-2">
              Filter out flights with more than this many stops.
            </p>
            <select
              value={prefs.max_stops ?? ""}
              onChange={(e) =>
                setPrefs((p) => ({
                  ...p,
                  max_stops: e.target.value ? Number(e.target.value) : null,
                }))
              }
              className="w-32 rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
            >
              <option value="">Any</option>
              <option value="0">Nonstop only</option>
              <option value="1">1 stop</option>
              <option value="2">2 stops</option>
              <option value="3">3 stops</option>
            </select>
          </div>

          {/* Max Layover Time */}
          <div>
            <label className="text-sm font-medium">Maximum Layover Time</label>
            <p className="text-xs text-muted-foreground mb-2">
              Filter out flights with layovers longer than this.
            </p>
            <select
              value={prefs.max_layover_minutes ?? ""}
              onChange={(e) =>
                setPrefs((p) => ({
                  ...p,
                  max_layover_minutes: e.target.value ? Number(e.target.value) : null,
                }))
              }
              className="w-32 rounded-md border border-border bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
            >
              <option value="">Any</option>
              {LAYOVER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Seat Preference */}
          <div>
            <label className="text-sm font-medium">Seat Preference</label>
            <p className="text-xs text-muted-foreground mb-2">
              Your preferred seat type (informational only).
            </p>
            <div className="flex gap-3">
              {SEAT_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm cursor-pointer transition-colors ${
                    prefs.seat_preference === opt.value
                      ? "border-primary bg-primary/5 text-primary font-medium"
                      : "border-border text-muted-foreground hover:bg-muted/50"
                  }`}
                >
                  <input
                    type="radio"
                    name="seat_preference"
                    value={opt.value}
                    checked={prefs.seat_preference === opt.value}
                    onChange={(e) =>
                      setPrefs((p) => ({ ...p, seat_preference: e.target.value }))
                    }
                    className="sr-only"
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </div>

          {/* Preferred Alliances */}
          <div>
            <label className="text-sm font-medium">Preferred Alliances</label>
            <p className="text-xs text-muted-foreground mb-2">
              Boost airlines from your preferred alliances in search results.
            </p>
            <div className="space-y-2">
              {ALLIANCE_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`flex items-center gap-3 rounded-md border px-3 py-2.5 cursor-pointer transition-colors ${
                    prefs.preferred_alliances.includes(opt.value)
                      ? "border-primary bg-primary/5"
                      : "border-border hover:bg-muted/50"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={prefs.preferred_alliances.includes(opt.value)}
                    onChange={(e) =>
                      setPrefs((p) => ({
                        ...p,
                        preferred_alliances: e.target.checked
                          ? [...p.preferred_alliances, opt.value]
                          : p.preferred_alliances.filter((a) => a !== opt.value),
                      }))
                    }
                    className="rounded"
                  />
                  <div>
                    <span className="text-sm font-medium">{opt.label}</span>
                    <p className="text-[11px] text-muted-foreground">{opt.airlines}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Prefer Same Tier */}
          <div className="flex items-center justify-between">
            <div>
              <label className="text-sm font-medium">Suggest Similar Quality Airlines</label>
              <p className="text-xs text-muted-foreground">
                When reviewing expensive selections, show alternatives from same-tier airlines
                (e.g. full-service to full-service) instead of only the absolute cheapest.
              </p>
            </div>
            <Switch
              checked={prefs.prefer_same_tier}
              onCheckedChange={(checked) =>
                setPrefs((p) => ({ ...p, prefer_same_tier: checked }))
              }
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save Preferences"}
        </Button>
        {saved && (
          <span className="text-sm text-emerald-600 font-medium">
            Preferences saved
          </span>
        )}
      </div>
    </div>
  );
}
