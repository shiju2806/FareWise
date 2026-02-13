import { create } from "zustand";
import type { Trip } from "@/types/trip";
import apiClient from "@/api/client";

interface TripState {
  trips: Trip[];
  currentTrip: Trip | null;
  loading: boolean;
  error: string | null;

  createTripNL: (input: string) => Promise<Trip>;
  createTripStructured: (legs: LegInput[]) => Promise<Trip>;
  fetchTrips: (status?: string) => Promise<void>;
  fetchTrip: (id: string) => Promise<void>;
  updateLegs: (tripId: string, legs: Record<string, unknown>[]) => Promise<Trip>;
  patchLeg: (legId: string, updates: Record<string, unknown>) => Promise<void>;
  deleteTrip: (tripId: string) => Promise<void>;
  clearCurrentTrip: () => void;
  clearError: () => void;
}

export interface LegInput {
  origin_city: string;
  destination_city: string;
  preferred_date: string;
  flexibility_days?: number;
  cabin_class?: string;
  passengers?: number;
}

export const useTripStore = create<TripState>((set, get) => ({
  trips: [],
  currentTrip: null,
  loading: false,
  error: null,

  createTripNL: async (input: string) => {
    set({ loading: true, error: null });
    try {
      const res = await apiClient.post("/trips", {
        natural_language_input: input,
      });
      const trip = res.data as Trip;
      set({ currentTrip: trip, loading: false });
      return trip;
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Failed to create trip";
      set({ error: msg, loading: false });
      throw err;
    }
  },

  createTripStructured: async (legs: LegInput[]) => {
    set({ loading: true, error: null });
    try {
      const res = await apiClient.post("/trips/structured", { legs });
      const trip = res.data as Trip;
      set({ currentTrip: trip, loading: false });
      return trip;
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Failed to create trip";
      set({ error: msg, loading: false });
      throw err;
    }
  },

  fetchTrips: async (status?: string) => {
    set({ loading: true, error: null });
    try {
      const params = status ? { status } : {};
      const res = await apiClient.get("/trips", { params });
      set({ trips: res.data as Trip[], loading: false });
    } catch {
      set({ error: "Failed to load trips", loading: false });
    }
  },

  fetchTrip: async (id: string) => {
    set({ loading: true, error: null });
    try {
      const res = await apiClient.get(`/trips/${id}`);
      set({ currentTrip: res.data as Trip, loading: false });
    } catch {
      set({ error: "Trip not found", loading: false });
    }
  },

  updateLegs: async (tripId: string, legs: Record<string, unknown>[]) => {
    set({ loading: true, error: null });
    try {
      const res = await apiClient.put(`/trips/${tripId}/legs`, { legs });
      const trip = res.data as Trip;
      set({ currentTrip: trip, loading: false });
      return trip;
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Failed to update legs";
      set({ error: msg, loading: false });
      throw err;
    }
  },

  patchLeg: async (legId: string, updates: Record<string, unknown>) => {
    try {
      const res = await apiClient.patch(`/trips/legs/${legId}`, updates);
      const updated = res.data as Trip["legs"][number];
      const trip = get().currentTrip;
      if (trip) {
        set({
          currentTrip: {
            ...trip,
            legs: trip.legs.map((l) => (l.id === legId ? { ...l, ...updated } : l)),
          },
        });
      }
    } catch (err) {
      throw err;
    }
  },

  deleteTrip: async (tripId: string) => {
    set({ loading: true, error: null });
    try {
      await apiClient.delete(`/trips/${tripId}`);
      set({
        trips: get().trips.filter((t) => t.id !== tripId),
        currentTrip: null,
        loading: false,
      });
    } catch {
      set({ error: "Failed to delete trip", loading: false });
    }
  },

  clearCurrentTrip: () => set({ currentTrip: null }),
  clearError: () => set({ error: null }),
}));
