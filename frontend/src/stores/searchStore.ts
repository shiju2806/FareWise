import { create } from "zustand";
import { persist } from "zustand/middleware";
import axios from "axios";
import type { SearchResult } from "@/types/search";
import apiClient from "@/api/client";

interface SearchState {
  results: Record<string, SearchResult>; // keyed by leg_id
  loading: boolean;
  sliderLoading: boolean;
  sliderValue: number;
  error: string | null;
  searchStartedAt: number | null;
  _abortController: AbortController | null;

  searchLeg: (legId: string) => Promise<void>;
  cancelSearch: () => void;
  rescoreWithSlider: (legId: string, position: number) => Promise<void>;
  setSliderValue: (v: number) => void;
  clearResults: () => void;
  clearError: () => void;
}

export const useSearchStore = create<SearchState>()(persist((set, get) => ({
  results: {},
  loading: false,
  sliderLoading: false,
  sliderValue: 40,
  error: null,
  searchStartedAt: null,
  _abortController: null,

  searchLeg: async (legId: string) => {
    // Cancel any in-flight search
    const prev = get()._abortController;
    if (prev) prev.abort();

    const controller = new AbortController();
    set({ loading: true, error: null, searchStartedAt: Date.now(), _abortController: controller });
    try {
      const res = await apiClient.post(
        `/search/${legId}`,
        { include_nearby_airports: true },
        { timeout: 120000, signal: controller.signal },
      );
      set((state) => ({
        results: { ...state.results, [legId]: res.data as SearchResult },
        loading: false,
        searchStartedAt: null,
        _abortController: null,
      }));
    } catch (err: unknown) {
      if (axios.isCancel(err)) {
        set({ loading: false, error: null, searchStartedAt: null, _abortController: null });
        return;
      }
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Search failed — try again";
      set({ error: msg, loading: false, searchStartedAt: null, _abortController: null });
    }
  },

  cancelSearch: () => {
    const ctrl = get()._abortController;
    if (ctrl) ctrl.abort();
    set({ loading: false, error: null, searchStartedAt: null, _abortController: null });
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
}), {
  name: "farewise-search",
  storage: {
    getItem: (name) => {
      const str = sessionStorage.getItem(name);
      return str ? JSON.parse(str) : null;
    },
    setItem: (name, value) => {
      try {
        sessionStorage.setItem(name, JSON.stringify(value));
      } catch {
        // sessionStorage full — silently ignore
      }
    },
    removeItem: (name) => sessionStorage.removeItem(name),
  },
  partialize: (state) => ({
    results: state.results,
    sliderValue: state.sliderValue,
  }),
}));
