import { useState, useRef, useEffect, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { useTripChatStore, type Block } from "@/stores/tripChatStore";

const EXAMPLES = [
  "Toronto to London next month",
  "Round trip SFO to Tokyo, March 15-22, business",
  "NYC to Chicago this Friday one way",
];

const SUGGESTION_MAP: Record<string, string[]> = {
  cabin_class: ["Economy", "Business", "Premium Economy", "First"],
  return_date: ["Round trip", "One way"],
  passengers: ["1 passenger", "2 passengers"],
  flexibility: ["Exact dates", "Flexible \u00b13 days"],
};

interface Props {
  onTripCreated: (tripId: string) => void;
}

/* ------------------------------------------------------------------ */
/*  BlockRenderer — renders structured blocks inline in chat          */
/* ------------------------------------------------------------------ */

function FlightCard({ block }: { block: Block }) {
  const [expanded, setExpanded] = useState(false);
  const { route, date, anchor, alternatives_count, price_range, alternatives } = block.data;
  const alts = (alternatives || []) as Array<{
    airline_code: string; airline_name: string; alliance: string;
    tier: string; price: number; stops: number; departure_time: string;
    duration_minutes: number | null; savings_vs_anchor: number; group: string;
  }>;

  return (
    <div className="my-2 rounded-lg border border-border bg-card p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-semibold text-sm">{route}</p>
          <p className="text-xs text-muted-foreground">{date}</p>
        </div>
        {anchor && (
          <p className="text-lg font-bold text-primary">
            ${Number(anchor.price).toLocaleString()}
          </p>
        )}
      </div>

      {anchor && (
        <div className="text-xs space-y-0.5">
          <p className="font-medium">
            {anchor.airline} {anchor.flight_number && `\u00b7 ${anchor.flight_number}`}
          </p>
          <p className="text-muted-foreground">
            {anchor.departure && `${String(anchor.departure).slice(11, 16)} departure`}
            {anchor.stops === 0 ? " \u00b7 Direct" : ` \u00b7 ${anchor.stops} stop`}
            {anchor.duration_minutes && ` \u00b7 ${Math.floor(anchor.duration_minutes / 60)}h ${anchor.duration_minutes % 60}m`}
          </p>
          {anchor.reason && (
            <p className="text-muted-foreground/70 italic text-[11px]">{anchor.reason}</p>
          )}
        </div>
      )}

      {alts.length > 0 ? (
        <div className="pt-1.5 border-t border-border">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-[11px] text-primary hover:underline flex items-center gap-1"
          >
            {expanded ? "Hide" : "Show"} {alts.length} alternative{alts.length !== 1 ? "s" : ""}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              className={`transition-transform ${expanded ? "rotate-180" : ""}`}>
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          {expanded && (
            <div className="mt-2 space-y-1">
              {alts.map((alt, idx) => (
                <div key={idx} className={`flex items-center justify-between text-xs px-2 py-1.5 rounded ${
                  alt.tier === "full_service" ? "bg-muted/50" : alt.tier === "low_cost" ? "bg-amber-50/50 dark:bg-amber-950/20" : "bg-muted/30"
                }`}>
                  <div className="min-w-0">
                    <span className={alt.tier === "low_cost" ? "text-muted-foreground" : "font-medium"}>
                      {alt.airline_name || alt.airline_code}
                    </span>
                    {alt.alliance !== "unaffiliated" && (
                      <span className="text-muted-foreground ml-1 text-[10px]">
                        {alt.alliance.replace(/_/g, " ")}
                      </span>
                    )}
                    {alt.tier === "low_cost" && (
                      <span className="ml-1 text-[9px] px-1 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300">
                        Budget
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-muted-foreground w-12">{alt.stops === 0 ? "Direct" : `${alt.stops} stop`}</span>
                    <span className="font-semibold w-16 text-right">${Number(alt.price).toLocaleString()}</span>
                    <span className={`text-[10px] w-10 text-right ${
                      alt.savings_vs_anchor > 0 ? "text-green-600 dark:text-green-400" :
                      alt.savings_vs_anchor < 0 ? "text-red-500" : ""
                    }`}>
                      {alt.savings_vs_anchor > 0 ? `-${Math.round(alt.savings_vs_anchor)}%` :
                       alt.savings_vs_anchor < 0 ? `+${Math.round(Math.abs(alt.savings_vs_anchor))}%` : ""}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : alternatives_count > 0 ? (
        <div className="pt-1.5 border-t border-border text-[11px] text-muted-foreground">
          {alternatives_count} alternatives from ${Number(price_range?.min || 0).toLocaleString()} to ${Number(price_range?.max || 0).toLocaleString()}
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  CompanionPrompt — structured companion input with quick-pick      */
/* ------------------------------------------------------------------ */

function CompanionPrompt({ block, onSendMessage }: { block: Block; onSendMessage: (text: string) => void }) {
  const [answered, setAnswered] = useState(false);
  const [mode, setMode] = useState<"idle" | "kids" | "custom">("idle");
  const [kidsCount, setKidsCount] = useState(1);
  const [customText, setCustomText] = useState("");

  const { question } = block.data;

  if (answered) return null;

  function send(text: string) {
    setAnswered(true);
    onSendMessage(text);
  }

  return (
    <div className="my-2 rounded-lg border border-border bg-card p-3 space-y-2">
      {question && <p className="text-sm">{question}</p>}
      <div className="flex flex-wrap gap-1.5">
        <button type="button" onClick={() => send("just me")}
          className="text-xs px-3 py-1.5 rounded-md border border-primary/30 text-primary hover:bg-primary/10 transition-colors flex items-center gap-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
          </svg>
          Solo
        </button>
        <button type="button" onClick={() => send("my partner")}
          className="text-xs px-3 py-1.5 rounded-md border border-primary/30 text-primary hover:bg-primary/10 transition-colors flex items-center gap-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
            <path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
          Partner
        </button>
        <button type="button" onClick={() => setMode("kids")}
          className="text-xs px-3 py-1.5 rounded-md border border-primary/30 text-primary hover:bg-primary/10 transition-colors flex items-center gap-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
            <path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
          Partner + Kids
        </button>
        <button type="button" onClick={() => setMode("custom")}
          className="text-xs px-3 py-1.5 rounded-md border border-primary/30 text-primary hover:bg-primary/10 transition-colors flex items-center gap-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round">
            <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
          </svg>
          Custom
        </button>
      </div>

      {mode === "kids" && (
        <div className="flex items-center gap-2 pt-1">
          <span className="text-xs text-muted-foreground">Number of kids:</span>
          <button type="button" onClick={() => setKidsCount(Math.max(1, kidsCount - 1))}
            className="w-6 h-6 rounded border border-input text-xs flex items-center justify-center hover:bg-muted">
            &minus;
          </button>
          <span className="text-sm font-medium w-4 text-center">{kidsCount}</span>
          <button type="button" onClick={() => setKidsCount(Math.min(6, kidsCount + 1))}
            className="w-6 h-6 rounded border border-input text-xs flex items-center justify-center hover:bg-muted">
            +
          </button>
          <Button size="sm" className="h-6 text-xs ml-2"
            onClick={() => send(`my partner and ${kidsCount} kid${kidsCount > 1 ? "s" : ""}`)}>
            Confirm
          </Button>
        </div>
      )}

      {mode === "custom" && (
        <div className="flex gap-2 pt-1">
          <input type="text" value={customText} onChange={(e) => setCustomText(e.target.value)}
            placeholder="e.g., 3 colleagues"
            className="flex-1 rounded-md border border-input bg-transparent px-2 py-1 text-xs"
            onKeyDown={(e) => { if (e.key === "Enter" && customText.trim()) send(customText.trim()); }}
          />
          <Button size="sm" className="h-6 text-xs" disabled={!customText.trim()}
            onClick={() => send(customText.trim())}>
            Send
          </Button>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  CompanionDatesPrompt — same dates or different?                   */
/* ------------------------------------------------------------------ */

function CompanionDatesPrompt({ block, onSendMessage }: { block: Block; onSendMessage: (text: string) => void }) {
  const [answered, setAnswered] = useState(false);

  const { question } = block.data;

  if (answered) return null;

  function send(text: string) {
    setAnswered(true);
    onSendMessage(text);
  }

  return (
    <div className="my-2 rounded-lg border border-border bg-card p-3 space-y-2">
      {question && <p className="text-sm">{question}</p>}
      <div className="flex flex-wrap gap-1.5">
        <button type="button" onClick={() => send("companions traveling on same dates as me")}
          className="text-xs px-3 py-1.5 rounded-md border border-primary/30 text-primary hover:bg-primary/10 transition-colors flex items-center gap-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round">
            <rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/>
            <line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/>
          </svg>
          Same dates as me
        </button>
        <button type="button" onClick={() => send("companions have different travel dates")}
          className="text-xs px-3 py-1.5 rounded-md border border-primary/30 text-primary hover:bg-primary/10 transition-colors flex items-center gap-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/>
            <path d="M3 10h18"/><path d="m14 14-4 4"/><path d="m10 14 4 4"/>
          </svg>
          Different dates
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  BlockRenderer — renders structured blocks inline in chat          */
/* ------------------------------------------------------------------ */

function BlockRenderer({ block, onSendMessage }: { block: Block; onSendMessage: (text: string) => void }) {
  if (block.type === "flight_card") return <FlightCard block={block} />;

  if (block.type === "companion_prompt") {
    return <CompanionPrompt block={block} onSendMessage={onSendMessage} />;
  }

  if (block.type === "companion_dates_prompt") {
    return <CompanionDatesPrompt block={block} onSendMessage={onSendMessage} />;
  }

  if (block.type === "budget_card") {
    const { anchor_total, total_travelers, recommended_cabin, reason, cabin_options,
            near_miss_note, savings_note, source } = block.data;

    return (
      <div className="my-2 rounded-lg border border-green-200 bg-green-50/80 dark:bg-green-950/20 dark:border-green-800 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-green-800 dark:text-green-300">
            Cabin Budget for {total_travelers} Travelers
          </p>
          <div className="flex items-center gap-1.5">
            {source === "llm" && (
              <span className="text-[9px] bg-violet-100 dark:bg-violet-900/50 text-violet-700 dark:text-violet-300 px-1.5 py-0.5 rounded-full">
                AI recommended
              </span>
            )}
            <p className="text-xs text-green-600 dark:text-green-400">
              Budget: ${Number(anchor_total).toLocaleString()}
            </p>
          </div>
        </div>

        <div className="space-y-1">
          {(cabin_options as { cabin: string; total_all_travelers: number; fits: boolean }[])?.map(
            (opt) => (
              <div
                key={opt.cabin}
                className={`flex justify-between items-center text-xs px-2 py-1 rounded ${
                  opt.cabin === recommended_cabin
                    ? "bg-green-100 dark:bg-green-900/40 font-semibold"
                    : ""
                }`}
              >
                <span className="capitalize">{opt.cabin.replace("_", " ")}</span>
                <span className={opt.fits ? "text-green-600 dark:text-green-400" : "text-red-500"}>
                  ${Number(opt.total_all_travelers).toLocaleString()} {opt.fits ? "\u2713" : "\u2717"}
                </span>
              </div>
            ),
          )}
        </div>

        <p className="text-[11px] text-green-700 dark:text-green-400 italic">{reason}</p>

        {near_miss_note && (
          <div className="text-[10px] bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300 px-2 py-1 rounded">
            {near_miss_note}
          </div>
        )}
        {savings_note && (
          <p className="text-[10px] text-green-600 dark:text-green-400">{savings_note}</p>
        )}
      </div>
    );
  }

  return null;
}

/* ------------------------------------------------------------------ */
/*  TripChat component                                                */
/* ------------------------------------------------------------------ */

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
          <div key={i}>
            <div
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-line ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-foreground"
                }`}
              >
                {msg.content}
              </div>
            </div>
            {/* Structured blocks after assistant messages */}
            {msg.role === "assistant" && msg.blocks && msg.blocks.length > 0 && (
              <div className="mt-1 max-w-[85%]">
                {msg.blocks.map((block, j) => (
                  <BlockRenderer key={j} block={block} onSendMessage={sendMessage} />
                ))}
              </div>
            )}
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
              {leg.origin_city} ({leg.origin_airport}) &rarr; {leg.destination_city} ({leg.destination_airport})
              <span className="text-green-600 dark:text-green-500 ml-1">
                {leg.preferred_date} &middot; {leg.cabin_class}
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
