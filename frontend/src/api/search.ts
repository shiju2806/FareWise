import apiClient from "./client";

export async function searchFlights(tripLegId: string, params?: Record<string, unknown>) {
  const { data } = await apiClient.post(`/search/${tripLegId}`, params);
  return data;
}

export async function getFlightOptions(tripLegId: string, date?: string, sort = "price") {
  const { data } = await apiClient.get(`/search/${tripLegId}/options`, { params: { date, sort } });
  return data;
}

export async function rescoreFlights(tripLegId: string, weights: Record<string, number>) {
  const { data } = await apiClient.post(`/search/${tripLegId}/score`, weights);
  return data;
}
