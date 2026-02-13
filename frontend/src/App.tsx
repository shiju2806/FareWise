import { useEffect } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { useAuthStore } from "@/stores/authStore";
import apiClient from "@/api/client";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import NewTrip from "@/pages/NewTrip";
import TripHistory from "@/pages/TripHistory";
import TripSearch from "@/pages/TripSearch";

function AuthLoader({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const setAuth = useAuthStore((s) => s.setAuth);
  const logout = useAuthStore((s) => s.logout);

  useEffect(() => {
    if (!token) return;
    apiClient
      .get("/users/me")
      .then((res) => setAuth(res.data, token))
      .catch(() => logout());
  }, [token, setAuth, logout]);

  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthLoader>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route path="/" element={<Dashboard />} />
            <Route path="/trips/new" element={<NewTrip />} />
            <Route path="/trips" element={<TripHistory />} />
            <Route path="/trips/:tripId/search" element={<TripSearch />} />
          </Route>
        </Routes>
      </AuthLoader>
    </BrowserRouter>
  );
}
