import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import NewTrip from "@/pages/NewTrip";
import TripHistory from "@/pages/TripHistory";
import TripSearch from "@/pages/TripSearch";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<AppShell />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/trips/new" element={<NewTrip />} />
          <Route path="/trips" element={<TripHistory />} />
          <Route path="/trips/:tripId/search" element={<TripSearch />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
