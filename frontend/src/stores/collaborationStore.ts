import { create } from "zustand";
import apiClient from "@/api/client";
import type { TripOverlap } from "@/types/collaboration";

interface CollaborationState {
  overlaps: TripOverlap[];
  loading: boolean;

  fetchOverlaps: (tripId: string) => Promise<void>;
  dismissOverlap: (overlapId: string) => Promise<void>;
}

export const useCollaborationStore = create<CollaborationState>((set) => ({
  overlaps: [],
  loading: false,

  fetchOverlaps: async (tripId: string) => {
    try {
      const res = await apiClient.get(`/trips/${tripId}/overlaps`);
      set({ overlaps: res.data });
    } catch {
      set({ overlaps: [] });
    }
  },

  dismissOverlap: async (overlapId: string) => {
    try {
      await apiClient.post(`/overlaps/${overlapId}/dismiss`);
      set((s) => ({
        overlaps: s.overlaps.map((o) =>
          o.id === overlapId ? { ...o, dismissed: true } : o
        ),
      }));
    } catch {
      // silent
    }
  },
}));
