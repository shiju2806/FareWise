import { create } from "zustand";
import apiClient from "@/api/client";
import type {
  GroupTripDetail,
  GroupTripSummary,
  TripOverlap,
} from "@/types/collaboration";

interface CollaborationState {
  overlaps: TripOverlap[];
  groupTrips: GroupTripSummary[];
  groupDetail: GroupTripDetail | null;
  loading: boolean;

  fetchOverlaps: (tripId: string) => Promise<void>;
  dismissOverlap: (overlapId: string) => Promise<void>;
  fetchGroupTrips: () => Promise<void>;
  fetchGroupDetail: (groupId: string) => Promise<void>;
  createGroupTrip: (params: {
    name: string;
    destination_city: string;
    start_date: string;
    end_date: string;
    notes?: string;
    member_emails?: string[];
  }) => Promise<string | null>;
  acceptInvite: (groupId: string) => Promise<void>;
  declineInvite: (groupId: string) => Promise<void>;
}

export const useCollaborationStore = create<CollaborationState>((set, get) => ({
  overlaps: [],
  groupTrips: [],
  groupDetail: null,
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

  fetchGroupTrips: async () => {
    set({ loading: true });
    try {
      const res = await apiClient.get("/group-trips");
      set({ groupTrips: res.data, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  fetchGroupDetail: async (groupId: string) => {
    set({ loading: true });
    try {
      const res = await apiClient.get(`/group-trips/${groupId}`);
      set({ groupDetail: res.data, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  createGroupTrip: async (params) => {
    set({ loading: true });
    try {
      const res = await apiClient.post("/group-trips", params);
      await get().fetchGroupTrips();
      set({ loading: false });
      return res.data.id;
    } catch {
      set({ loading: false });
      return null;
    }
  },

  acceptInvite: async (groupId: string) => {
    try {
      await apiClient.post(`/group-trips/${groupId}/accept`);
      await get().fetchGroupTrips();
    } catch {
      // silent
    }
  },

  declineInvite: async (groupId: string) => {
    try {
      await apiClient.post(`/group-trips/${groupId}/decline`);
      await get().fetchGroupTrips();
    } catch {
      // silent
    }
  },
}));
