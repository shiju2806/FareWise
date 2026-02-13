import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { NotificationBell } from "@/components/notifications/NotificationBell";

export function AppShell() {
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const navItems = [
    { label: "New Trip", path: "/trips/new", primary: true, roles: null },
    { label: "My Trips", path: "/trips", primary: false, roles: null },
    { label: "Approvals", path: "/approvals", primary: false, roles: ["manager", "admin"] },
    { label: "Dashboard", path: "/", primary: false, roles: null },
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
            const isActive =
              item.path === "/"
                ? location.pathname === "/"
                : location.pathname.startsWith(item.path);
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
            <button
              onClick={logout}
              className="mt-2 text-xs text-muted-foreground hover:text-foreground"
            >
              Sign out
            </button>
          </div>
        )}
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="max-w-5xl mx-auto p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
