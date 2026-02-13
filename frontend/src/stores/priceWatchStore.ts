import { create } from "zustand";
import apiClient from "@/api/client";
import type { PriceWatch, Alert } from "@/types/priceWatch";

interface PriceWatchState {
  watches: PriceWatch[];
  alerts: Alert[];
  unreadAlertCount: number;
  loadingWatches: boolean;
  loadingAlerts: boolean;
  creating: boolean;

  fetchWatches: () => Promise<void>;
  createWatch: (params: {
    watch_type?: string;
    origin?: string;
    destination?: string;
    target_date: string;
    flexibility_days?: number;
    target_price?: number;
    cabin_class?: string;
    current_price?: number;
  }) => Promise<void>;
  deleteWatch: (watchId: string) => Promise<void>;
  fetchAlerts: () => Promise<void>;
}

export const usePriceWatchStore = create<PriceWatchState>((set) => ({
  watches: [],
  alerts: [],
  unreadAlertCount: 0,
  loadingWatches: false,
  loadingAlerts: false,
  creating: false,

  fetchWatches: async () => {
    set({ loadingWatches: true });
    try {
      const res = await apiClient.get("/price-watches");
      set({ watches: res.data.watches, loadingWatches: false });
    } catch {
      set({ loadingWatches: false });
    }
  },

  createWatch: async (params) => {
    set({ creating: true });
    try {
      await apiClient.post("/price-watches", params);
      // Refetch
      const res = await apiClient.get("/price-watches");
      set({ watches: res.data.watches, creating: false });
    } catch {
      set({ creating: false });
    }
  },

  deleteWatch: async (watchId: string) => {
    try {
      await apiClient.delete(`/price-watches/${watchId}`);
      set((state) => ({
        watches: state.watches.filter((w) => w.id !== watchId),
      }));
    } catch {
      // silent
    }
  },

  fetchAlerts: async () => {
    set({ loadingAlerts: true });
    try {
      const res = await apiClient.get("/alerts");
      set({
        alerts: res.data.alerts,
        unreadAlertCount: res.data.unread_count,
        loadingAlerts: false,
      });
    } catch {
      set({ loadingAlerts: false });
    }
  },
}));
