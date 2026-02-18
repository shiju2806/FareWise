import { create } from "zustand";
import apiClient from "@/api/client";
import type {
  AnalyticsOverview,
  DepartmentAnalytics,
  LeaderboardData,
  MyStats,
  RouteAnalytics,
  SavingsGoal,
  SavingsSummary,
} from "@/types/analytics";

interface AnalyticsState {
  overview: AnalyticsOverview | null;
  department: DepartmentAnalytics | null;
  route: RouteAnalytics | null;
  savingsSummary: SavingsSummary | null;
  savingsGoal: SavingsGoal | null;
  myStats: MyStats | null;
  leaderboard: LeaderboardData | null;
  loading: boolean;

  fetchOverview: () => Promise<void>;
  fetchDepartment: (dept: string) => Promise<void>;
  fetchRoute: (origin: string, dest: string) => Promise<void>;
  fetchSavingsSummary: () => Promise<void>;
  fetchSavingsGoal: () => Promise<void>;
  fetchMyStats: () => Promise<void>;
  fetchLeaderboard: (department?: string) => Promise<void>;
}

export const useAnalyticsStore = create<AnalyticsState>((set) => ({
  overview: null,
  department: null,
  route: null,
  savingsSummary: null,
  savingsGoal: null,
  myStats: null,
  leaderboard: null,
  loading: false,

  fetchOverview: async () => {
    set({ loading: true });
    try {
      const res = await apiClient.get("/analytics/overview");
      set({ overview: res.data, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  fetchDepartment: async (dept: string) => {
    set({ loading: true });
    try {
      const res = await apiClient.get(`/analytics/department/${encodeURIComponent(dept)}`);
      set({ department: res.data, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  fetchRoute: async (origin: string, dest: string) => {
    set({ loading: true });
    try {
      const res = await apiClient.get(`/analytics/route/${origin}/${dest}`);
      set({ route: res.data, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  fetchSavingsSummary: async () => {
    set({ loading: true });
    try {
      const res = await apiClient.get("/analytics/savings-report");
      set({ savingsSummary: res.data, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  fetchSavingsGoal: async () => {
    try {
      const res = await apiClient.get("/analytics/savings-goal");
      set({ savingsGoal: res.data });
    } catch {
      /* ignore */
    }
  },

  fetchMyStats: async () => {
    set({ loading: true });
    try {
      const res = await apiClient.get("/analytics/my-stats");
      set({ myStats: res.data, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  fetchLeaderboard: async (department?: string) => {
    set({ loading: true });
    try {
      const params = department ? `?department=${encodeURIComponent(department)}` : "";
      const res = await apiClient.get(`/analytics/leaderboard${params}`);
      set({ leaderboard: res.data, loading: false });
    } catch {
      set({ loading: false });
    }
  },
}));
