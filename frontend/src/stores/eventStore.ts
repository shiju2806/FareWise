import { create } from "zustand";
import type { LegEventsResponse, DateEvent } from "@/types/event";
import apiClient from "@/api/client";

interface EventState {
  legEvents: Record<string, LegEventsResponse>; // keyed by leg_id
  loading: boolean;
  error: string | null;

  fetchLegEvents: (legId: string) => Promise<void>;
  getDateEvents: (legId: string, date: string) => DateEvent[];
  clearEvents: () => void;
}

export const useEventStore = create<EventState>((set, get) => ({
  legEvents: {},
  loading: false,
  error: null,

  fetchLegEvents: async (legId: string) => {
    // Skip if already loaded
    if (get().legEvents[legId]) return;

    set({ loading: true, error: null });
    try {
      const res = await apiClient.get(`/events/search/${legId}`);
      set((state) => ({
        legEvents: { ...state.legEvents, [legId]: res.data as LegEventsResponse },
        loading: false,
      }));
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Failed to load events";
      set({ error: msg, loading: false });
    }
  },

  getDateEvents: (legId: string, date: string): DateEvent[] => {
    const leg = get().legEvents[legId];
    if (!leg) return [];
    return leg.date_events[date] || [];
  },

  clearEvents: () => set({ legEvents: {}, error: null }),
}));
