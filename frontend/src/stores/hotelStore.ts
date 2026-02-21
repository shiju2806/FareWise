import { create } from "zustand";
import type { HotelSearchResult } from "@/types/hotel";
import apiClient from "@/api/client";

interface HotelState {
  results: Record<string, HotelSearchResult>; // keyed by leg_id
  loading: boolean;
  error: string | null;

  searchHotels: (
    legId: string,
    checkIn: string,
    checkOut: string,
    guests?: number,
    maxRate?: number | null,
    maxStars?: number | null,
    sortBy?: string
  ) => Promise<void>;

  selectHotel: (
    legId: string,
    hotelOptionId: string,
    checkIn: string,
    checkOut: string,
    note?: string
  ) => Promise<void>;

  clearResults: () => void;
}

export const useHotelStore = create<HotelState>((set, _get) => ({
  results: {},
  loading: false,
  error: null,

  searchHotels: async (legId, checkIn, checkOut, guests = 1, maxRate, maxStars, sortBy = "value") => {
    set({ loading: true, error: null });
    try {
      const res = await apiClient.post(`/search/${legId}/hotels`, {
        check_in: checkIn,
        check_out: checkOut,
        guests,
        max_nightly_rate: maxRate,
        max_stars: maxStars,
        sort_by: sortBy,
      });
      set((state) => ({
        results: { ...state.results, [legId]: res.data as HotelSearchResult },
        loading: false,
      }));
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Hotel search failed";
      set({ error: msg, loading: false });
    }
  },

  selectHotel: async (legId, hotelOptionId, checkIn, checkOut, note) => {
    try {
      await apiClient.post(`/search/${legId}/hotels/select`, {
        hotel_option_id: hotelOptionId,
        check_in: checkIn,
        check_out: checkOut,
        justification_note: note,
      });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Hotel selection failed";
      set({ error: msg });
    }
  },

  clearResults: () => set({ results: {}, error: null }),
}));
