import { create } from "zustand";
import apiClient from "@/api/client";
import type { Trip } from "@/types/trip";

export interface Block {
  type: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: Record<string, any>;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  blocks?: Block[];
}

interface PartialTrip {
  confidence: number;
  legs: {
    sequence: number;
    origin_city: string;
    origin_airport: string;
    destination_city: string;
    destination_airport: string;
    preferred_date: string;
    flexibility_days: number;
    cabin_class: string;
    passengers: number;
  }[];
  companions?: number;
  companion_cabin_class?: string;
  companions_same_dates?: boolean | null;
  interpretation_notes?: string;
  _agent_state?: Record<string, unknown>;
}

interface TripChatState {
  messages: ChatMessage[];
  conversationHistory: { role: string; content: string }[];
  partialTrip: PartialTrip | null;
  tripReady: boolean;
  missingFields: string[];
  loading: boolean;
  error: string | null;

  sendMessage: (text: string) => Promise<void>;
  injectAssistantMessage: (text: string) => void;
  createFromChat: () => Promise<Trip | null>;
  reset: () => void;
}

const STORAGE_KEY = "farewise-trip-chat";

function _loadPersisted(): Partial<TripChatState> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const saved = JSON.parse(raw);
    return {
      messages: saved.messages ?? [],
      conversationHistory: saved.conversationHistory ?? [],
      partialTrip: saved.partialTrip ?? null,
      tripReady: saved.tripReady ?? false,
      missingFields: saved.missingFields ?? [],
    };
  } catch {
    return {};
  }
}

function _persist(state: TripChatState) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        messages: state.messages,
        conversationHistory: state.conversationHistory,
        partialTrip: state.partialTrip,
        tripReady: state.tripReady,
        missingFields: state.missingFields,
      }),
    );
  } catch { /* localStorage full — non-critical */ }
}

const persisted = _loadPersisted();

export const useTripChatStore = create<TripChatState>((set, get) => ({
  messages: (persisted.messages as ChatMessage[]) ?? [],
  conversationHistory: (persisted.conversationHistory as { role: string; content: string }[]) ?? [],
  partialTrip: (persisted.partialTrip as PartialTrip | null) ?? null,
  tripReady: persisted.tripReady ?? false,
  missingFields: (persisted.missingFields as string[]) ?? [],
  loading: false,
  error: null,

  injectAssistantMessage: (text: string) => {
    const state = get();
    const msg: ChatMessage = { role: "assistant", content: text };
    set({
      messages: [...state.messages, msg],
      conversationHistory: [...state.conversationHistory, { role: "assistant", content: text }],
    });
  },

  sendMessage: async (text: string) => {
    const state = get();
    const userMsg: ChatMessage = { role: "user", content: text };
    set({ messages: [...state.messages, userMsg], loading: true, error: null });

    try {
      const res = await apiClient.post("/trips/chat", {
        message: text,
        conversation_history: state.conversationHistory,
        partial_trip: state.partialTrip,
      });

      const data = res.data as {
        reply: string;
        conversation_history: { role: string; content: string }[];
        partial_trip: PartialTrip | null;
        trip_ready: boolean;
        missing_fields: string[];
        blocks?: Block[];
      };

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: data.reply,
        blocks: data.blocks || [],
      };

      set({
        messages: [...get().messages, assistantMsg],
        conversationHistory: data.conversation_history,
        partialTrip: data.partial_trip,
        tripReady: data.trip_ready,
        missingFields: data.missing_fields,
        loading: false,
      });
      _persist(get());
    } catch {
      set({ loading: false, error: "Failed to process message" });
    }
  },

  createFromChat: async () => {
    const { partialTrip, messages, conversationHistory } = get();
    if (!partialTrip || !partialTrip.legs?.length) return null;

    set({ loading: true, error: null });
    try {
      const legs = partialTrip.legs.map((l) => ({
        origin_city: l.origin_city,
        destination_city: l.destination_city,
        preferred_date: l.preferred_date,
        flexibility_days: l.flexibility_days || 3,
        cabin_class: l.cabin_class || "economy",
        passengers: l.passengers || 1,
      }));

      const res = await apiClient.post("/trips/structured", { legs });
      const trip = res.data as Trip;

      // If companion data exists, update the trip with it
      if (partialTrip.companions && partialTrip.companions > 0) {
        try {
          await apiClient.post(`/trips/${trip.id}/companion-pricing`, {
            companions: partialTrip.companions,
            companion_cabin_class: partialTrip.companion_cabin_class || "economy",
          });
        } catch { /* companion pricing will be fetched later */ }
      }

      // Persist the planning conversation so SearchAssistant can continue it
      try {
        sessionStorage.setItem(
          `farewise-assistant-${trip.id}`,
          JSON.stringify({
            messages,
            history: conversationHistory,
            companions_same_dates: partialTrip.companions_same_dates,
          }),
        );
      } catch { /* sessionStorage full */ }

      set({ loading: false });
      return trip;
    } catch {
      set({ loading: false, error: "Failed to create trip" });
      return null;
    }
  },

  reset: () => {
    localStorage.removeItem(STORAGE_KEY);
    set({
      messages: [],
      conversationHistory: [],
      partialTrip: null,
      tripReady: false,
      missingFields: [],
      loading: false,
      error: null,
    });
  },
}));
