import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { ToastContainer } from "@/components/shared/ToastContainer";
import { OnboardingTour } from "@/components/onboarding/OnboardingTour";
import { useAuthStore } from "@/stores/authStore";
import apiClient from "@/api/client";

// Lazy-loaded pages for code splitting
const Login = lazy(() => import("@/pages/Login"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Trips = lazy(() => import("@/pages/Trips"));
const TripSearch = lazy(() => import("@/pages/TripSearch"));
const TripReview = lazy(() => import("@/pages/TripReview"));
const TripAudit = lazy(() => import("@/pages/TripAudit"));
const ApprovalDashboard = lazy(() => import("@/pages/ApprovalDashboard"));
const ApprovalDetailPage = lazy(() => import("@/pages/ApprovalDetailPage"));
const PolicyManagement = lazy(() => import("@/pages/PolicyManagement"));
const PriceWatches = lazy(() => import("@/pages/PriceWatches"));
const AnalyticsDashboard = lazy(() => import("@/pages/AnalyticsDashboard"));
const MyProfile = lazy(() => import("@/pages/MyProfile"));
const MyStats = lazy(() => import("@/pages/MyStats"));
const LeaderboardPage = lazy(() => import("@/pages/LeaderboardPage"));
const GroupTrips = lazy(() => import("@/pages/GroupTrips"));
const GroupTripDetailPage = lazy(() => import("@/pages/GroupTripDetailPage"));
const AlertFeed = lazy(() => import("@/pages/AlertFeed"));

function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
    </div>
  );
}

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
    <ErrorBoundary>
    <BrowserRouter>
      <AuthLoader>
        <Suspense fallback={<PageLoader />}>
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
            <Route path="/trips/new" element={<Navigate to="/trips?new=1" replace />} />
            <Route path="/trips" element={<Trips />} />
            <Route path="/trips/:tripId/search" element={<TripSearch />} />
            <Route path="/trips/:tripId/review" element={<TripReview />} />
            <Route path="/trips/:tripId/audit" element={<TripAudit />} />
            <Route path="/price-watches" element={<PriceWatches />} />
            <Route path="/approvals" element={<ApprovalDashboard />} />
            <Route path="/approvals/:approvalId" element={<ApprovalDetailPage />} />
            <Route path="/analytics" element={<AnalyticsDashboard />} />
            <Route path="/profile" element={<MyProfile />} />
            <Route path="/my-stats" element={<MyStats />} />
            <Route path="/leaderboard" element={<LeaderboardPage />} />
            <Route path="/group-trips" element={<GroupTrips />} />
            <Route path="/group-trips/:groupId" element={<GroupTripDetailPage />} />
            <Route path="/alerts" element={<AlertFeed />} />
            <Route path="/policies" element={<PolicyManagement />} />
          </Route>
        </Routes>
        </Suspense>
      </AuthLoader>
      <ToastContainer />
      <OnboardingTour />
    </BrowserRouter>
    </ErrorBoundary>
  );
}
