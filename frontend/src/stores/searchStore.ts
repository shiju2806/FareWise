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

  // Background prefetch state
  prefetching: Record<string, boolean>;
  _prefetchControllers: Record<string, AbortController>;

  searchLeg: (legId: string) => Promise<void>;
  refreshLeg: (legId: string) => Promise<void>;
  cancelSearch: () => void;
  prefetchLeg: (legId: string) => Promise<void>;
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
  prefetching: {},
  _prefetchControllers: {},

  searchLeg: async (legId: string) => {
    // Cancel any in-flight main search
    const prev = get()._abortController;
    if (prev) prev.abort();

    // Cancel any in-flight prefetch for THIS specific leg (avoid duplicate work)
    const prefetchCtrl = get()._prefetchControllers[legId];
    if (prefetchCtrl) {
      prefetchCtrl.abort();
      set((state) => {
        const nextControllers = { ...state._prefetchControllers };
        delete nextControllers[legId];
        return {
          prefetching: { ...state.prefetching, [legId]: false },
          _prefetchControllers: nextControllers,
        };
      });
    }

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

  refreshLeg: async (legId: string) => {
    // Silent re-search: updates results in-place without loading skeleton.
    // Used when passenger count changes so prices update without UI disruption.

    // Cancel any in-flight loud search (it has stale params)
    const prev = get()._abortController;
    if (prev) prev.abort();
    set({ loading: false, searchStartedAt: null, _abortController: null });

    try {
      const res = await apiClient.post(
        `/search/${legId}`,
        { include_nearby_airports: true },
        { timeout: 120000 },
      );
      set((state) => ({
        results: { ...state.results, [legId]: res.data as SearchResult },
      }));
    } catch {
      // Silent failure — existing results remain visible
    }
  },

  cancelSearch: () => {
    const ctrl = get()._abortController;
    if (ctrl) ctrl.abort();
    set({ loading: false, error: null, searchStartedAt: null, _abortController: null });
  },

  prefetchLeg: async (legId: string) => {
    // Skip if results already exist or already prefetching this leg
    if (get().results[legId] || get().prefetching[legId]) return;

    const controller = new AbortController();
    set((state) => ({
      prefetching: { ...state.prefetching, [legId]: true },
      _prefetchControllers: { ...state._prefetchControllers, [legId]: controller },
    }));

    try {
      const res = await apiClient.post(
        `/search/${legId}`,
        { include_nearby_airports: true },
        { timeout: 120000, signal: controller.signal },
      );
      set((state) => {
        const nextControllers = { ...state._prefetchControllers };
        delete nextControllers[legId];
        return {
          results: { ...state.results, [legId]: res.data as SearchResult },
          prefetching: { ...state.prefetching, [legId]: false },
          _prefetchControllers: nextControllers,
        };
      });
    } catch (err: unknown) {
      if (!axios.isCancel(err)) {
        console.warn(`Prefetch for leg ${legId} failed:`, err);
      }
      set((state) => {
        const nextControllers = { ...state._prefetchControllers };
        delete nextControllers[legId];
        return {
          prefetching: { ...state.prefetching, [legId]: false },
          _prefetchControllers: nextControllers,
        };
      });
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
