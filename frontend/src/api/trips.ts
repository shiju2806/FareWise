import apiClient from "./client";

export async function createTripNL(naturalLanguageInput: string) {
  const { data } = await apiClient.post("/trips", { natural_language_input: naturalLanguageInput });
  return data;
}

export async function createTripStructured(legs: unknown[]) {
  const { data } = await apiClient.post("/trips/structured", { legs });
  return data;
}

export async function listTrips(params?: { status?: string; page?: number; limit?: number }) {
  const { data } = await apiClient.get("/trips", { params });
  return data;
}

export async function getTrip(tripId: string) {
  const { data } = await apiClient.get(`/trips/${tripId}`);
  return data;
}

export async function deleteTrip(tripId: string) {
  const { data } = await apiClient.delete(`/trips/${tripId}`);
  return data;
}
