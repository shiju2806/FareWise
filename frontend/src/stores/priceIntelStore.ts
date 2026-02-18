import { create } from "zustand";
import type { MonthCalendarData, PriceAdvice, PriceTrend, PriceContext, MatrixEntry } from "@/types/search";
import apiClient from "@/api/client";

interface PriceIntelState {
  monthData: Record<string, MonthCalendarData>;
  monthLoading: Record<string, boolean>;
  monthError: Record<string, boolean>;

  matrixData: Record<string, MatrixEntry[]>;
  matrixLoading: Record<string, boolean>;

  advice: Record<string, PriceAdvice>;
  adviceLoading: Record<string, boolean>;

  trends: Record<string, PriceTrend>;
  trendLoading: Record<string, boolean>;

  priceContext: Record<string, PriceContext>;
  priceContextLoading: Record<string, boolean>;

  fetchMonthCalendar: (legId: string, year: number, month: number) => Promise<void>;
  fetchMonthMatrix: (legId: string, year: number, month: number) => Promise<void>;
  fetchAdvice: (legId: string) => Promise<void>;
  fetchTrend: (legId: string) => Promise<void>;
  fetchPriceContext: (legId: string, date: string) => Promise<void>;
}

export const usePriceIntelStore = create<PriceIntelState>((set, get) => ({
  monthData: {},
  monthLoading: {},
  monthError: {},
  matrixData: {},
  matrixLoading: {},
  advice: {},
  adviceLoading: {},
  trends: {},
  trendLoading: {},
  priceContext: {},
  priceContextLoading: {},

  fetchMonthCalendar: async (legId: string, year: number, month: number) => {
    const key = `${legId}:${year}-${String(month).padStart(2, "0")}`;
    const existing = get().monthData[key];
    // Re-fetch if cached result had no dates (stale empty response)
    const hasData = existing && Object.keys(existing.dates || {}).length > 0;
    if (hasData || get().monthLoading[key]) return;

    set((s) => ({
      monthLoading: { ...s.monthLoading, [key]: true },
      monthError: { ...s.monthError, [key]: false },
    }));

    try {
      const res = await apiClient.get(
        `/search/${legId}/calendar?year=${year}&month=${month}`
      );
      set((s) => ({
        monthData: { ...s.monthData, [key]: res.data as MonthCalendarData },
        monthLoading: { ...s.monthLoading, [key]: false },
      }));
    } catch {
      set((s) => ({
        monthLoading: { ...s.monthLoading, [key]: false },
        monthError: { ...s.monthError, [key]: true },
      }));
    }
  },

  fetchMonthMatrix: async (legId: string, year: number, month: number) => {
    const key = `${legId}:${year}-${String(month).padStart(2, "0")}`;
    if (get().matrixData[key] || get().matrixLoading[key]) return;

    set((s) => ({ matrixLoading: { ...s.matrixLoading, [key]: true } }));

    try {
      const res = await apiClient.get(
        `/search/${legId}/matrix?year=${year}&month=${month}`
      );
      set((s) => ({
        matrixData: { ...s.matrixData, [key]: (res.data as any).entries as MatrixEntry[] },
        matrixLoading: { ...s.matrixLoading, [key]: false },
      }));
    } catch {
      set((s) => ({ matrixLoading: { ...s.matrixLoading, [key]: false } }));
    }
  },

  fetchAdvice: async (legId: string) => {
    if (get().advice[legId] || get().adviceLoading[legId]) return;

    set((s) => ({ adviceLoading: { ...s.adviceLoading, [legId]: true } }));

    try {
      const res = await apiClient.get(`/search/${legId}/advisor`);
      set((s) => ({
        advice: { ...s.advice, [legId]: res.data as PriceAdvice },
        adviceLoading: { ...s.adviceLoading, [legId]: false },
      }));
    } catch {
      set((s) => ({ adviceLoading: { ...s.adviceLoading, [legId]: false } }));
    }
  },

  fetchTrend: async (legId: string) => {
    if (get().trends[legId] || get().trendLoading[legId]) return;

    set((s) => ({ trendLoading: { ...s.trendLoading, [legId]: true } }));

    try {
      const res = await apiClient.get(`/search/${legId}/price-trend`);
      set((s) => ({
        trends: { ...s.trends, [legId]: res.data as PriceTrend },
        trendLoading: { ...s.trendLoading, [legId]: false },
      }));
    } catch {
      set((s) => ({ trendLoading: { ...s.trendLoading, [legId]: false } }));
    }
  },

  fetchPriceContext: async (legId: string, date: string) => {
    const key = `${legId}:${date}`;
    const cached = get().priceContext[key];
    // Re-fetch if cached result was unavailable (stale failure)
    if ((cached && cached.available) || get().priceContextLoading[key]) return;

    set((s) => ({
      priceContextLoading: { ...s.priceContextLoading, [key]: true },
    }));

    try {
      const res = await apiClient.get(
        `/search/${legId}/price-context?target_date=${date}`
      );
      set((s) => ({
        priceContext: { ...s.priceContext, [key]: res.data as PriceContext },
        priceContextLoading: { ...s.priceContextLoading, [key]: false },
      }));
    } catch {
      set((s) => ({
        priceContext: {
          ...s.priceContext,
          [key]: { available: false, message: "Failed to load" },
        },
        priceContextLoading: { ...s.priceContextLoading, [key]: false },
      }));
    }
  },
}));
