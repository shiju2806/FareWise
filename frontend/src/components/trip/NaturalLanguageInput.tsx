import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

interface Props {
  onSubmit: (input: string) => Promise<void>;
  loading: boolean;
}

const EXAMPLES = [
  "Toronto to New York next Friday, returning Sunday",
  "Round trip SFO to London, March 15-22, business class",
  "Multi-city: Chicago \u2192 Miami \u2192 Denver \u2192 Chicago, April 1-10",
];

export function NaturalLanguageInput({ onSubmit, loading }: Props) {
  const [text, setText] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    await onSubmit(text.trim());
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Describe your trip</CardTitle>
        <CardDescription>
          Tell us where you want to go in plain English. Our AI will parse your
          itinerary.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (text.trim() && !loading) {
                  onSubmit(text.trim());
                }
              }
            }}
            placeholder="e.g. Round trip from Toronto to New York next Friday, returning Sunday evening, economy class"
            className="w-full min-h-[100px] rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] outline-none resize-y"
            rows={4}
          />
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={loading || !text.trim()}>
              {loading ? "Searching..." : "Search"}
            </Button>
            <span className="text-xs text-muted-foreground">
              Press Enter to search
            </span>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">
              Try an example:
            </p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => setText(ex)}
                  className="text-xs px-2 py-1 rounded-md bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors cursor-pointer hover:ring-1 hover:ring-primary/30"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
