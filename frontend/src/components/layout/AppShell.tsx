import { useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { NotificationBell } from "@/components/notifications/NotificationBell";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { KeyboardShortcutsModal } from "@/components/shared/KeyboardShortcutsModal";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";

export function AppShell() {
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const [showShortcuts, setShowShortcuts] = useState(false);

  useKeyboardShortcuts(() => setShowShortcuts((v) => !v));

  const navItems = [
    { label: "Trips", path: "/trips", primary: true, roles: null },
    { label: "Price Watches", path: "/price-watches", primary: false, roles: null },
    { label: "My Stats", path: "/my-stats", primary: false, roles: null },
    { label: "Leaderboard", path: "/leaderboard", primary: false, roles: null },
    { label: "Approvals", path: "/approvals", primary: false, roles: ["manager", "admin"] },
    { label: "Analytics", path: "/analytics", primary: false, roles: ["manager", "admin"] },
    { label: "Policies", path: "/policies", primary: false, roles: ["admin"] },
  ];

  const visibleItems = navItems.filter(
    (item) => !item.roles || (user && item.roles.includes(user.role))
  );

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-60 border-r border-border flex flex-col">
        <div className="p-6 flex items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight">FareWise</h1>
          <NotificationBell />
        </div>
        <nav className="flex-1 px-3 space-y-1">
          {visibleItems.map((item) => {
            const isActive = location.pathname === item.path
              || location.pathname.startsWith(item.path + "/");
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`block px-3 py-2 rounded-md text-sm ${
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                } ${item.primary ? "font-medium" : ""}`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        {user && (
          <div className="p-4 border-t border-border">
            <p className="text-sm font-medium">
              {user.first_name} {user.last_name}
            </p>
            <p className="text-xs text-muted-foreground capitalize">
              {user.role}
              {user.department && ` · ${user.department}`}
            </p>
            <div className="flex items-center justify-between mt-2">
              <button
                onClick={logout}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Sign out
              </button>
              <ThemeToggle />
            </div>
          </div>
        )}
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="max-w-5xl mx-auto p-8">
          <Outlet />
        </div>
      </main>

      <KeyboardShortcutsModal
        open={showShortcuts}
        onClose={() => setShowShortcuts(false)}
      />
    </div>
  );
}
