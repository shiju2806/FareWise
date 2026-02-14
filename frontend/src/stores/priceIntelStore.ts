import { create } from "zustand";
import type { MonthCalendarData, PriceAdvice, PriceTrend } from "@/types/search";
import apiClient from "@/api/client";

interface PriceIntelState {
  monthData: Record<string, MonthCalendarData>;
  monthLoading: Record<string, boolean>;
  monthError: Record<string, boolean>;

  advice: Record<string, PriceAdvice>;
  adviceLoading: Record<string, boolean>;

  trends: Record<string, PriceTrend>;
  trendLoading: Record<string, boolean>;

  fetchMonthCalendar: (legId: string, year: number, month: number) => Promise<void>;
  fetchAdvice: (legId: string) => Promise<void>;
  fetchTrend: (legId: string) => Promise<void>;
}

export const usePriceIntelStore = create<PriceIntelState>((set, get) => ({
  monthData: {},
  monthLoading: {},
  monthError: {},
  advice: {},
  adviceLoading: {},
  trends: {},
  trendLoading: {},

  fetchMonthCalendar: async (legId: string, year: number, month: number) => {
    const key = `${legId}:${year}-${String(month).padStart(2, "0")}`;
    if (get().monthData[key] || get().monthLoading[key]) return;

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
}));
