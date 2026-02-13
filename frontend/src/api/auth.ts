import apiClient from "./client";

export async function login(email: string, password: string) {
  const { data } = await apiClient.post("/auth/login", { email, password });
  return data;
}

export async function register(payload: {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  role?: string;
  department?: string;
}) {
  const { data } = await apiClient.post("/auth/register", payload);
  return data;
}
