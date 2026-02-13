import { create } from "zustand";
import apiClient from "@/api/client";

interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  reference_type: string | null;
  reference_id: string | null;
  is_read: boolean;
  created_at: string;
}

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  loading: boolean;
  fetch: () => Promise<void>;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
}

export const useNotificationStore = create<NotificationState>((set) => ({
  notifications: [],
  unreadCount: 0,
  loading: false,
  fetch: async () => {
    set({ loading: true });
    try {
      const res = await apiClient.get("/notifications?limit=20");
      set({
        notifications: res.data.notifications,
        unreadCount: res.data.unread_count,
        loading: false,
      });
    } catch {
      set({ loading: false });
    }
  },
  markRead: async (id: string) => {
    await apiClient.put(`/notifications/${id}/read`);
    set((state) => ({
      notifications: state.notifications.map((n) =>
        n.id === id ? { ...n, is_read: true } : n
      ),
      unreadCount: Math.max(0, state.unreadCount - 1),
    }));
  },
  markAllRead: async () => {
    await apiClient.put("/notifications/read-all");
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, is_read: true })),
      unreadCount: 0,
    }));
  },
}));
