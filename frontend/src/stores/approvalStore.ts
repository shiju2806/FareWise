import { create } from "zustand";
import apiClient from "@/api/client";

interface ApprovalTrip {
  id: string;
  title: string;
  traveler: { id: string; name: string; department: string | null };
  total_estimated_cost: number | null;
  legs_count: number;
  travel_dates: string;
}

interface ApprovalSavings {
  policy_status: string | null;
  savings_vs_expensive: number | null;
  premium_vs_cheapest: number | null;
  narrative: string | null;
}

interface ApprovalItem {
  id: string;
  trip: ApprovalTrip;
  savings_report: ApprovalSavings | null;
  warnings_count: number;
  violations_count: number;
  status: string;
  created_at: string;
}

interface ApprovalState {
  approvals: ApprovalItem[];
  counts: { pending: number; approved: number; rejected: number };
  loading: boolean;
  error: string | null;
  fetchApprovals: (status?: string) => Promise<void>;
  decide: (
    approvalId: string,
    action: string,
    comments?: string
  ) => Promise<void>;
}

export const useApprovalStore = create<ApprovalState>((set) => ({
  approvals: [],
  counts: { pending: 0, approved: 0, rejected: 0 },
  loading: false,
  error: null,
  fetchApprovals: async (status?: string) => {
    set({ loading: true, error: null });
    try {
      const params = status ? `?status=${status}` : "";
      const res = await apiClient.get(`/approvals${params}`);
      set({
        approvals: res.data.approvals,
        counts: res.data.counts,
        loading: false,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load approvals";
      set({ loading: false, error: message });
    }
  },
  decide: async (approvalId: string, action: string, comments?: string) => {
    await apiClient.post(`/approvals/${approvalId}/decide`, {
      action,
      comments,
    });
  },
}));
