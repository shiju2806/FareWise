import { create } from "zustand";
import apiClient from "@/api/client";
import type { Trip } from "@/types/trip";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
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
  interpretation_notes?: string;
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
  createFromChat: () => Promise<Trip | null>;
  reset: () => void;
}

export const useTripChatStore = create<TripChatState>((set, get) => ({
  messages: [],
  conversationHistory: [],
  partialTrip: null,
  tripReady: false,
  missingFields: [],
  loading: false,
  error: null,

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
      };

      const assistantMsg: ChatMessage = { role: "assistant", content: data.reply };

      set({
        messages: [...get().messages, assistantMsg],
        conversationHistory: data.conversation_history,
        partialTrip: data.partial_trip,
        tripReady: data.trip_ready,
        missingFields: data.missing_fields,
        loading: false,
      });
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

      // Persist the planning conversation so SearchAssistant can continue it
      try {
        sessionStorage.setItem(
          `farewise-assistant-${trip.id}`,
          JSON.stringify({ messages, history: conversationHistory }),
        );
      } catch { /* sessionStorage full */ }

      set({ loading: false });
      return trip;
    } catch {
      set({ loading: false, error: "Failed to create trip" });
      return null;
    }
  },

  reset: () =>
    set({
      messages: [],
      conversationHistory: [],
      partialTrip: null,
      tripReady: false,
      missingFields: [],
      loading: false,
      error: null,
    }),
}));
