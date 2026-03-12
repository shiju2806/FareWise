import { useState, useRef, useEffect, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import apiClient from "@/api/client";
import type { TripLeg, CompanionPricing, CabinBudgetResult } from "@/types/trip";
import type { SearchResult } from "@/types/search";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface Props {
  tripId: string;
  activeLeg: TripLeg;
  legsCount: number;
  onTripUpdated: () => void;
  searchResults?: Record<string, SearchResult>;
}

const QUICK_ACTIONS = [
  { label: "Book a new trip", icon: "🔍" },
  { label: "Add return flight", icon: "↩" },
  { label: "Change to business class", icon: "✈" },
  { label: "Search ±3 days flexibility", icon: "📅" },
  { label: "My family is joining this trip", icon: "👨‍👩‍👧‍👦" },
];

const STORAGE_PREFIX = "farewise-assistant-";

function loadChat(tripId: string): { messages: ChatMessage[]; history: { role: string; content: string }[] } {
  try {
    const raw = sessionStorage.getItem(STORAGE_PREFIX + tripId);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return { messages: [], history: [] };
}

function saveChat(tripId: string, messages: ChatMessage[], history: { role: string; content: string }[]) {
  try {
    sessionStorage.setItem(STORAGE_PREFIX + tripId, JSON.stringify({ messages, history }));
  } catch { /* sessionStorage full */ }
}

export function SearchAssistant({ tripId, activeLeg, legsCount, onTripUpdated, searchResults }: Props) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadChat(tripId).messages);
  const [conversationHistory, setConversationHistory] = useState<{ role: string; content: string }[]>(() => loadChat(tripId).history);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [companionPricing, setCompanionPricing] = useState<CompanionPricing | null>(null);
  const [cabinBudget, setCabinBudget] = useState<CabinBudgetResult | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Persist conversation to sessionStorage on change
  useEffect(() => {
    if (messages.length > 0) {
      saveChat(tripId, messages, conversationHistory);
    }
  }, [tripId, messages, conversationHistory]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // Build trip context for the chat
  function getTripContext(): string {
    let ctx = `Current trip: ${activeLeg.origin_city} (${activeLeg.origin_airport}) → ${activeLeg.destination_city} (${activeLeg.destination_airport}) on ${activeLeg.preferred_date}, ${activeLeg.cabin_class}, ${activeLeg.passengers} pax. ${legsCount} leg(s) total. Trip ID: ${tripId}`;
    if (activeLeg.companion_preferred_date && activeLeg.companion_preferred_date !== activeLeg.preferred_date) {
      ctx += `. Companions fly on ${activeLeg.companion_preferred_date} (different from employee)`;
    }
    return ctx;
  }

  async function sendMessage(text: string) {
    const userMsg: ChatMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      // Include trip context in the first message
      const contextPrefix = conversationHistory.length === 0 ? `[Context: ${getTripContext()}] ` : "";

      const res = await apiClient.post("/trips/chat", {
        message: contextPrefix + text,
        conversation_history: conversationHistory,
        partial_trip: null,
      });

      const data = res.data as {
        reply: string;
        conversation_history: { role: string; content: string }[];
        partial_trip?: {
          companions?: number;
          companion_cabin_class?: string;
        } | null;
      };

      const assistantMsg: ChatMessage = { role: "assistant", content: data.reply };
      setMessages((prev) => [...prev, assistantMsg]);
      setConversationHistory(data.conversation_history);

      // If companion info detected, fetch cabin budget recommendation
      const companions = data.partial_trip?.companions;
      if (companions && companions > 0) {
        // Collect anchor prices from search results
        const anchorPrices: Record<string, number> = {};
        if (searchResults) {
          for (const [legId, sr] of Object.entries(searchResults)) {
            if (sr.anchor) {
              anchorPrices[legId] = sr.anchor.price;
            }
          }
        }

        // If we have anchors, use the cabin budget engine
        if (Object.keys(anchorPrices).length > 0) {
          try {
            const totalTravelers = 1 + companions; // employee + companions
            const budgetRes = await apiClient.post(`/trips/${tripId}/cabin-budget`, {
              total_travelers: totalTravelers,
              anchor_prices: anchorPrices,
            });
            const budgetResult = budgetRes.data as CabinBudgetResult;
            setCabinBudget(budgetResult);
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: budgetResult.recommendation_reason },
            ]);
          } catch {
            // Fall back to companion pricing
            try {
              const cabin = data.partial_trip?.companion_cabin_class || "economy";
              const pricingRes = await apiClient.post(`/trips/${tripId}/companion-pricing`, {
                companions,
                companion_cabin_class: cabin,
              });
              const pricing = pricingRes.data as CompanionPricing;
              setCompanionPricing(pricing);
              if (pricing.summary) {
                setMessages((prev) => [
                  ...prev,
                  { role: "assistant", content: pricing.summary },
                ]);
              }
            } catch {
              // Both failed — don't break the chat
            }
          }
        } else {
          // No anchors — use existing companion pricing
          try {
            const cabin = data.partial_trip?.companion_cabin_class || "economy";
            const pricingRes = await apiClient.post(`/trips/${tripId}/companion-pricing`, {
              companions,
              companion_cabin_class: cabin,
            });
            const pricing = pricingRes.data as CompanionPricing;
            setCompanionPricing(pricing);
            if (pricing.summary) {
              setMessages((prev) => [
                ...prev,
                { role: "assistant", content: pricing.summary },
              ]);
            }
          } catch {
            // Companion pricing failed — don't break the chat
          }
        }
      }

      // Check if the response suggests a trip modification was needed
      // Apply quick actions directly
      await applyAction(text);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "Sorry, I couldn't process that. Try again." }]);
    } finally {
      setLoading(false);
    }
  }

  async function applyAction(text: string) {
    const lower = text.toLowerCase();

    try {
      if (lower.includes("return flight") || lower.includes("round trip")) {
        // Add return leg
        await apiClient.post(`/trips/${tripId}/add-leg`, {
          origin_city: activeLeg.destination_city,
          destination_city: activeLeg.origin_city,
          preferred_date: activeLeg.preferred_date, // Will be adjusted by user
          flexibility_days: activeLeg.flexibility_days,
          cabin_class: activeLeg.cabin_class,
          passengers: activeLeg.passengers,
        });
        onTripUpdated();
      } else if (lower.includes("business class")) {
        await apiClient.patch(`/trips/legs/${activeLeg.id}`, {
          cabin_class: "business",
        });
        onTripUpdated();
      } else if (lower.includes("premium economy")) {
        await apiClient.patch(`/trips/legs/${activeLeg.id}`, {
          cabin_class: "premium_economy",
        });
        onTripUpdated();
      } else if (lower.includes("first class")) {
        await apiClient.patch(`/trips/legs/${activeLeg.id}`, {
          cabin_class: "first",
        });
        onTripUpdated();
      } else if (lower.includes("flexibility") || lower.includes("±3") || lower.includes("flexible")) {
        await apiClient.patch(`/trips/legs/${activeLeg.id}`, {
          flexibility_days: 3,
        });
        onTripUpdated();
      }
    } catch {
      // Action failed — chat reply will still show
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;
    const text = input.trim();
    setInput("");
    await sendMessage(text);
  }

  function handleQuickAction(label: string) {
    sendMessage(label);
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-30 w-12 h-12 rounded-full bg-primary text-primary-foreground shadow-lg hover:shadow-xl transition-all flex items-center justify-center"
        title="Trip Assistant"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
          />
        </svg>
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-30 w-[340px] h-[420px] bg-card border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-bottom-4 duration-200">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-muted/30">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500" />
          <span className="text-xs font-semibold">Trip Assistant</span>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="p-1 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-2 p-3">
        {messages.length === 0 && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Need to modify your trip? I can help.
            </p>
            <div className="space-y-1.5">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  onClick={() => handleQuickAction(action.label)}
                  className="w-full text-left text-xs px-2.5 py-2 rounded-md bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors flex items-center gap-2"
                >
                  <span>{action.icon}</span>
                  {action.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-lg px-2.5 py-1.5 text-xs ${
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
            <div className="bg-muted rounded-lg px-2.5 py-1.5">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-muted-foreground/50 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-1.5 h-1.5 bg-muted-foreground/50 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-1.5 h-1.5 bg-muted-foreground/50 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}

        {cabinBudget && cabinBudget.cabin_options.length > 0 && (
          <div className="bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 rounded-lg p-2.5 text-xs space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-emerald-900 dark:text-emerald-100">
                Cabin Budget Recommendation
              </span>
              {cabinBudget.source === "llm" && (
                <span className="text-[9px] bg-violet-100 dark:bg-violet-900/50 text-violet-700 dark:text-violet-300 px-1.5 py-0.5 rounded-full">
                  AI recommended
                </span>
              )}
            </div>
            <div className="space-y-1 text-emerald-800 dark:text-emerald-200">
              <div className="flex justify-between">
                <span>Budget (anchor total)</span>
                <span className="font-medium">${cabinBudget.budget_envelope.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span>Travelers</span>
                <span className="font-medium">{cabinBudget.total_travelers}</span>
              </div>
              {cabinBudget.cabin_options.map((opt) => (
                <div
                  key={opt.cabin_class}
                  className={`flex justify-between items-center px-1.5 py-0.5 rounded ${
                    opt.cabin_class === cabinBudget.recommended_cabin
                      ? "bg-emerald-100 dark:bg-emerald-900/50 font-semibold"
                      : ""
                  }`}
                >
                  <span className="capitalize flex items-center gap-1">
                    {opt.cabin_class.replace("_", " ")}
                    {opt.cabin_class === cabinBudget.recommended_cabin && (
                      <span className="text-[9px] bg-emerald-200 dark:bg-emerald-800 text-emerald-800 dark:text-emerald-200 px-1 rounded">
                        recommended
                      </span>
                    )}
                  </span>
                  <span className={opt.fits_budget ? "text-emerald-700 dark:text-emerald-300" : "text-red-600 dark:text-red-400"}>
                    ${opt.total_all_travelers.toLocaleString()}
                    {!opt.fits_budget && " (over)"}
                  </span>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-emerald-700 dark:text-emerald-300 italic">
              {cabinBudget.recommendation_reason}
            </p>
            {cabinBudget.near_miss_note && (
              <div className="text-[10px] bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300 px-2 py-1 rounded">
                {cabinBudget.near_miss_note}
              </div>
            )}
            {cabinBudget.savings_note && (
              <p className="text-[10px] text-emerald-600 dark:text-emerald-400">
                {cabinBudget.savings_note}
              </p>
            )}
            {!cabinBudget.savings_note && cabinBudget.economy_savings > 0 && (
              <div className="text-[10px] text-emerald-600 dark:text-emerald-400">
                Economy saves ${cabinBudget.economy_savings.toLocaleString()} vs your business class budget
              </div>
            )}
          </div>
        )}

        {companionPricing && companionPricing.companion_options.length > 0 && !cabinBudget && (
          <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-lg p-2.5 text-xs space-y-2">
            <div className="font-semibold text-blue-900 dark:text-blue-100">
              Family Travel Pricing
            </div>
            <div className="space-y-1 text-blue-800 dark:text-blue-200">
              <div className="flex justify-between">
                <span>Your {activeLeg.cabin_class}</span>
                <span className="font-medium">${companionPricing.employee_total.toLocaleString()}</span>
              </div>
              {companionPricing.companion_options.map((opt) => (
                <div key={`${opt.leg_id}-${opt.cabin_class}`} className="flex justify-between">
                  <span>{opt.route} ({opt.cabin_class})</span>
                  <span>${opt.per_person.toLocaleString()}/person</span>
                </div>
              ))}
              <div className="border-t border-blue-200 dark:border-blue-700 pt-1 flex justify-between font-semibold">
                <span>Combined ({companionPricing.companions_count + 1} travelers)</span>
                <span>
                  ${companionPricing.combined_min.toLocaleString()}
                  {companionPricing.combined_max !== companionPricing.combined_min &&
                    `–$${companionPricing.combined_max.toLocaleString()}`}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="flex gap-1.5 p-2 border-t border-border">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your trip..."
          className="flex-1 rounded-md border border-input bg-transparent px-2.5 py-1.5 text-xs shadow-xs placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] outline-none"
          disabled={loading}
        />
        <Button type="submit" size="sm" className="h-7 text-xs px-2" disabled={loading || !input.trim()}>
          Send
        </Button>
      </form>
    </div>
  );
}
