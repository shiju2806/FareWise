import { create } from "zustand";
import apiClient from "@/api/client";

interface Policy {
  id: string;
  name: string;
  description: string | null;
  rule_type: string;
  conditions: Record<string, unknown>;
  threshold: Record<string, unknown>;
  action: string;
  severity: number;
  exception_roles: string[];
  is_active: boolean;
  created_at: string | null;
}

interface PolicyState {
  policies: Policy[];
  loading: boolean;
  error: string | null;
  fetch: () => Promise<void>;
  create: (data: Omit<Policy, "id" | "is_active" | "created_at">) => Promise<void>;
  update: (id: string, data: Partial<Policy>) => Promise<void>;
  remove: (id: string) => Promise<void>;
}

export const usePolicyStore = create<PolicyState>((set) => ({
  policies: [],
  loading: false,
  error: null,
  fetch: async () => {
    set({ loading: true, error: null });
    try {
      const res = await apiClient.get("/policies");
      set({ policies: res.data.policies, loading: false });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load policies";
      set({ loading: false, error: message });
    }
  },
  create: async (data) => {
    await apiClient.post("/policies", data);
    const res = await apiClient.get("/policies");
    set({ policies: res.data.policies });
  },
  update: async (id, data) => {
    await apiClient.put(`/policies/${id}`, data);
    const res = await apiClient.get("/policies");
    set({ policies: res.data.policies });
  },
  remove: async (id) => {
    await apiClient.delete(`/policies/${id}`);
    set((state) => ({
      policies: state.policies.filter((p) => p.id !== id),
    }));
  },
}));
