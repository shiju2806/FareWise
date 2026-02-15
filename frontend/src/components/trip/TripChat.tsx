import { useState, useRef, useEffect, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { useTripChatStore } from "@/stores/tripChatStore";

const EXAMPLES = [
  "Toronto to London next month",
  "Round trip SFO to Tokyo, March 15-22, business",
  "NYC to Chicago this Friday one way",
];

const SUGGESTION_MAP: Record<string, string[]> = {
  cabin_class: ["Economy", "Business", "Premium Economy", "First"],
  return_date: ["Round trip", "One way"],
  passengers: ["1 passenger", "2 passengers"],
  flexibility: ["Exact dates", "Flexible ±3 days"],
};

interface Props {
  onTripCreated: (tripId: string) => void;
}

export function TripChat({ onTripCreated }: Props) {
  const {
    messages,
    partialTrip,
    tripReady,
    missingFields,
    loading,
    error,
    sendMessage,
    createFromChat,
    reset,
  } = useTripChatStore();

  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;
    const text = input.trim();
    setInput("");
    await sendMessage(text);
  }

  async function handleCreate() {
    const trip = await createFromChat();
    if (trip) {
      onTripCreated(trip.id);
      reset();
    }
  }

  function handleSuggestion(text: string) {
    sendMessage(text);
  }

  // Compute which suggestion chips to show
  const suggestionChips = missingFields.flatMap(
    (field) => SUGGESTION_MAP[field] || []
  );

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-3 px-1 pb-3">
        {messages.length === 0 && (
          <div className="space-y-3 pt-4">
            <p className="text-sm text-muted-foreground">
              Describe your trip and I'll help you plan it.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => { setInput(ex); }}
                  className="text-xs px-2.5 py-1.5 rounded-md bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-foreground"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-muted rounded-lg px-3 py-2">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-muted-foreground/50 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-1.5 h-1.5 bg-muted-foreground/50 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-1.5 h-1.5 bg-muted-foreground/50 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Suggestion chips */}
      {suggestionChips.length > 0 && !loading && (
        <div className="flex flex-wrap gap-1.5 px-1 pb-2">
          {suggestionChips.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => handleSuggestion(chip)}
              className="text-[11px] px-2 py-1 rounded-full border border-primary/30 text-primary hover:bg-primary/10 transition-colors"
            >
              {chip}
            </button>
          ))}
        </div>
      )}

      {/* Trip ready card */}
      {tripReady && partialTrip && (
        <div className="mx-1 mb-2 rounded-lg border border-green-200 bg-green-50/80 dark:bg-green-950/20 dark:border-green-800 p-3 space-y-2">
          <p className="text-xs font-semibold text-green-800 dark:text-green-300">
            Trip ready!
          </p>
          {partialTrip.legs.map((leg, i) => (
            <div key={i} className="text-xs text-green-700 dark:text-green-400">
              {leg.origin_city} ({leg.origin_airport}) → {leg.destination_city} ({leg.destination_airport})
              <span className="text-green-600 dark:text-green-500 ml-1">
                {leg.preferred_date} · {leg.cabin_class}
              </span>
            </div>
          ))}
          <Button size="sm" onClick={handleCreate} disabled={loading} className="w-full mt-1">
            {loading ? "Creating..." : "Create Trip & Search"}
          </Button>
        </div>
      )}

      {error && (
        <p className="text-xs text-destructive px-1 pb-1">{error}</p>
      )}

      {/* Input bar */}
      <form onSubmit={handleSubmit} className="flex gap-2 px-1 pt-2 border-t border-border">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={messages.length === 0 ? "Where do you want to go?" : "Reply..."}
          className="flex-1 rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] outline-none"
          disabled={loading}
        />
        <Button type="submit" size="sm" disabled={loading || !input.trim()}>
          Send
        </Button>
      </form>
    </div>
  );
}
