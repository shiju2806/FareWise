import { create } from "zustand";
import type { SearchResult } from "@/types/search";
import apiClient from "@/api/client";

interface SearchState {
  results: Record<string, SearchResult>; // keyed by leg_id
  loading: boolean;
  sliderLoading: boolean;
  sliderValue: number;
  error: string | null;

  searchLeg: (legId: string) => Promise<void>;
  rescoreWithSlider: (legId: string, position: number) => Promise<void>;
  setSliderValue: (v: number) => void;
  clearResults: () => void;
  clearError: () => void;
}

export const useSearchStore = create<SearchState>((set, get) => ({
  results: {},
  loading: false,
  sliderLoading: false,
  sliderValue: 40,
  error: null,

  searchLeg: async (legId: string) => {
    set({ loading: true, error: null });
    try {
      const res = await apiClient.post(`/search/${legId}`, {
        include_nearby_airports: true,
      });
      set((state) => ({
        results: { ...state.results, [legId]: res.data as SearchResult },
        loading: false,
      }));
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Search failed";
      set({ error: msg, loading: false });
    }
  },

  rescoreWithSlider: async (legId: string, position: number) => {
    set({ sliderLoading: true, sliderValue: position });
    try {
      const res = await apiClient.post(
        `/search/${legId}/slider?slider_position=${position}`
      );
      const data = res.data as {
        recommendation: SearchResult["recommendation"];
        rescored_options: SearchResult["all_options"];
      };

      set((state) => {
        const existing = state.results[legId];
        if (!existing) return { sliderLoading: false };
        return {
          results: {
            ...state.results,
            [legId]: {
              ...existing,
              recommendation: data.recommendation,
              all_options: data.rescored_options,
            },
          },
          sliderLoading: false,
        };
      });
    } catch {
      set({ sliderLoading: false });
    }
  },

  setSliderValue: (v) => set({ sliderValue: v }),
  clearResults: () => set({ results: {} }),
  clearError: () => set({ error: null }),
}));
