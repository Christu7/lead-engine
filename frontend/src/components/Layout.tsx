import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

const navItems = [
  { to: "/", label: "Dashboard" },
  { to: "/leads", label: "Leads" },
  { to: "/companies", label: "Companies" },
  { to: "/scoring-rules", label: "Scoring Rules" },
  { to: "/settings", label: "Settings" },
];

export default function Layout() {
  const { user, switchClient, logout } = useAuth();

  const showSelector = user && user.clients.length > 1;

  return (
    <div className="flex h-screen bg-gray-100">
      <aside className="flex w-64 flex-col bg-gray-900 text-white">
        <div className="px-6 py-5 text-xl font-bold">LeadEngine</div>
        <nav className="flex-1 space-y-1 px-3">
          {navItems.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm font-medium ${
                  isActive ? "bg-gray-800 text-white" : "text-gray-300 hover:bg-gray-800 hover:text-white"
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-2 px-3 py-4">
          {showSelector && (
            <select
              value={user.active_client_id ?? ""}
              onChange={(e) => switchClient(Number(e.target.value))}
              className="w-full rounded-md bg-gray-800 px-3 py-2 text-sm font-medium text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {user.clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          )}
          <button
            onClick={logout}
            className="w-full rounded-md bg-gray-800 px-3 py-2 text-sm font-medium text-gray-300 hover:bg-gray-700 hover:text-white"
          >
            Logout
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto p-8">
        <Outlet />
      </main>
    </div>
  );
}
