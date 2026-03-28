import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { createClient } from "../api/client";
import { getQueueStats, type QueueStats } from "../api/admin";
import { useAuth } from "../contexts/AuthContext";

function ClientSelector() {
  const { user, switchClient, clientVersion } = useAuth();
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
        setAdding(false);
        setNewName("");
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  useEffect(() => {
    if (adding) inputRef.current?.focus();
  }, [adding]);

  if (!user) return null;

  // Only superadmins can create clients
  const isSuperAdmin = user.role === "superadmin";
  const activeClient = user.clients.find((c) => c.id === user.active_client_id);

  async function handleSwitch(clientId: number, clientName: string) {
    if (clientId === user!.active_client_id || switching) return;
    setOpen(false);
    setSwitching(true);
    try {
      await switchClient(clientId);
      setToast(`Switched to ${clientName}`);
      setTimeout(() => setToast(null), 3000);
    } finally {
      setSwitching(false);
    }
  }

  async function handleCreate() {
    const name = newName.trim();
    if (!name || creating) return;
    setCreating(true);
    try {
      const created = await createClient(name);
      setAdding(false);
      setNewName("");
      setOpen(false);
      await switchClient(created.id);
      setToast(`Created and switched to ${created.name}`);
      setTimeout(() => setToast(null), 3000);
    } catch {
      setToast("Failed to create workspace");
      setTimeout(() => setToast(null), 3000);
    } finally {
      setCreating(false);
    }
  }

  void clientVersion;

  return (
    <>
      <div ref={dropdownRef} className="relative px-3 mb-1">
        <button
          onClick={() => !switching && setOpen((o) => !o)}
          disabled={switching}
          className="w-full flex items-center justify-between rounded-md px-3 py-2 text-sm text-gray-400 hover:bg-gray-800 hover:text-gray-100 transition-colors disabled:opacity-60"
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          <span className="truncate text-left leading-tight">
            <span className="block text-[10px] uppercase tracking-widest text-gray-600 mb-0.5">
              Workspace
            </span>
            <span className="text-gray-200 font-medium">
              {activeClient?.name ?? "—"}
            </span>
          </span>
          {switching ? (
            <svg className="ml-2 h-3.5 w-3.5 animate-spin text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          ) : (
            <svg className="ml-2 h-3.5 w-3.5 text-gray-500 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 9l4-4 4 4M8 15l4 4 4-4" />
            </svg>
          )}
        </button>

        {open && (
          <div role="listbox" className="absolute left-3 right-3 top-full z-50 mt-1 rounded-md bg-gray-800 shadow-xl border border-gray-700 py-1 overflow-hidden">
            {user.clients.map((c) => {
              const isActive = c.id === user.active_client_id;
              return (
                <button
                  key={c.id}
                  role="option"
                  aria-selected={isActive}
                  onClick={() => handleSwitch(c.id, c.name)}
                  className={`w-full flex items-center justify-between px-3 py-2 text-sm transition-colors ${
                    isActive
                      ? "text-white bg-gray-700 cursor-default"
                      : "text-gray-300 hover:bg-gray-700 hover:text-white"
                  }`}
                >
                  <span className="truncate">{c.name}</span>
                  {isActive && (
                    <svg className="ml-2 h-3.5 w-3.5 text-indigo-400 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </button>
              );
            })}

            {/* New workspace — superadmin only */}
            {isSuperAdmin && (
              <>
                <div className="border-t border-gray-700 my-1" />
                {adding ? (
                  <div className="px-2 py-1.5 flex items-center gap-1.5">
                    <input
                      ref={inputRef}
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleCreate();
                        if (e.key === "Escape") { setAdding(false); setNewName(""); }
                      }}
                      placeholder="Workspace name"
                      className="flex-1 min-w-0 rounded bg-gray-700 px-2 py-1 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    <button
                      onClick={handleCreate}
                      disabled={!newName.trim() || creating}
                      className="rounded bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                    >
                      {creating ? "…" : "Add"}
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setAdding(true)}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:bg-gray-700 hover:text-gray-200 transition-colors"
                  >
                    <svg className="h-3.5 w-3.5 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                    </svg>
                    <span>New workspace</span>
                  </button>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {toast && (
        <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[9999] rounded-md bg-gray-900 border border-gray-700 px-4 py-2 text-sm text-white shadow-lg pointer-events-none">
          {toast}
        </div>
      )}
    </>
  );
}

function QueueIndicator() {
  const [stats, setStats] = useState<QueueStats | null>(null);
  const [open, setOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchStats() {
      try {
        const s = await getQueueStats();
        if (!cancelled) setStats(s);
      } catch {
        // silently ignore — superadmin-only endpoint
      }
    }
    fetchStats();
    const id = setInterval(fetchStats, 10_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  if (!stats) return null;

  const active = stats.pending + stats.processing + stats.scheduled;
  if (active === 0 && stats.dead_letter === 0) return null;

  const hasDeadLetters = stats.dead_letter > 0;

  return (
    <div ref={popoverRef} className="relative px-3 pb-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className={`w-full flex items-center gap-2 rounded-md px-3 py-1.5 text-xs transition-colors ${
          hasDeadLetters
            ? "text-red-400 hover:bg-gray-800"
            : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
        }`}
      >
        <span className={`h-1.5 w-1.5 rounded-full flex-shrink-0 ${
          stats.processing > 0 ? "bg-indigo-400 animate-pulse" : hasDeadLetters ? "bg-red-400" : "bg-yellow-400"
        }`} />
        <span>
          {stats.processing > 0
            ? `${stats.processing} processing`
            : stats.pending > 0
            ? `${stats.pending} task${stats.pending !== 1 ? "s" : ""} pending`
            : stats.scheduled > 0
            ? `${stats.scheduled} scheduled`
            : `${stats.dead_letter} dead letter${stats.dead_letter !== 1 ? "s" : ""}`}
        </span>
      </button>

      {open && (
        <div className="absolute bottom-full left-3 right-3 mb-1 rounded-md bg-gray-800 border border-gray-700 p-3 text-xs shadow-xl z-50">
          <p className="text-gray-400 uppercase tracking-wide text-[10px] mb-2">Queue</p>
          <div className="space-y-1">
            <div className="flex justify-between text-gray-300">
              <span>Pending</span><span>{stats.pending}</span>
            </div>
            <div className="flex justify-between text-gray-300">
              <span>Scheduled</span><span>{stats.scheduled}</span>
            </div>
            <div className="flex justify-between text-gray-300">
              <span>Processing</span><span>{stats.processing}</span>
            </div>
            {stats.dead_letter > 0 && (
              <div className="flex justify-between text-red-400 font-medium">
                <span>Dead letters</span><span>{stats.dead_letter}</span>
              </div>
            )}
          </div>
          {Object.keys(stats.tasks_by_type).length > 0 && (
            <>
              <p className="text-gray-400 uppercase tracking-wide text-[10px] mt-3 mb-2">By type</p>
              <div className="space-y-1">
                {Object.entries(stats.tasks_by_type).map(([type, count]) => (
                  <div key={type} className="flex justify-between text-gray-300">
                    <span className="truncate">{type.replace("_", " ")}</span>
                    <span>{count}</span>
                  </div>
                ))}
              </div>
            </>
          )}
          {stats.rate_limited_until && (
            <p className="text-yellow-400 mt-2 text-[10px]">
              Rate limit lifts {new Date(stats.rate_limited_until * 1000).toLocaleTimeString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const { user, logout, clientVersion } = useAuth();

  const isSuperAdmin = user?.role === "superadmin";
  const canAccessSettings = user?.role === "admin" || user?.role === "superadmin";

  // Show workspace selector for superadmins (always) or anyone with >1 client
  const showSelector = user && (isSuperAdmin || user.clients.length > 1);

  return (
    <div className="flex h-screen bg-gray-100">
      <aside className="flex w-64 flex-col bg-gray-900 text-white">
        <div className="px-6 py-5 text-xl font-bold">LeadEngine</div>

        {showSelector && (
          <div className="pb-2 border-b border-gray-800 mb-2">
            <ClientSelector />
          </div>
        )}

        <nav className="flex-1 space-y-1 px-3">
          <NavLink to="/" end className={({ isActive }) =>
            `block rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-gray-800 text-white" : "text-gray-300 hover:bg-gray-800 hover:text-white"}`
          }>Dashboard</NavLink>

          <NavLink to="/leads" className={({ isActive }) =>
            `block rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-gray-800 text-white" : "text-gray-300 hover:bg-gray-800 hover:text-white"}`
          }>Leads</NavLink>

          <NavLink to="/companies" className={({ isActive }) =>
            `block rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-gray-800 text-white" : "text-gray-300 hover:bg-gray-800 hover:text-white"}`
          }>Companies</NavLink>

          {/* Settings + Scoring Rules: admin and superadmin only */}
          {canAccessSettings && (
            <>
              <NavLink to="/scoring-rules" className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-gray-800 text-white" : "text-gray-300 hover:bg-gray-800 hover:text-white"}`
              }>Scoring Rules</NavLink>

              <NavLink to="/settings" className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-gray-800 text-white" : "text-gray-300 hover:bg-gray-800 hover:text-white"}`
              }>Settings</NavLink>
            </>
          )}

          {/* Super Admin panel: superadmin only */}
          {isSuperAdmin && (
            <>
              <div className="my-2 border-t border-gray-800" />
              <NavLink to="/super-admin" className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-indigo-800 text-white" : "text-indigo-400 hover:bg-gray-800 hover:text-indigo-300"}`
              }>Super Admin</NavLink>
            </>
          )}
        </nav>

        {isSuperAdmin && <QueueIndicator />}

        <div className="px-3 py-4">
          <button
            onClick={logout}
            className="w-full rounded-md bg-gray-800 px-3 py-2 text-sm font-medium text-gray-300 hover:bg-gray-700 hover:text-white"
          >
            Logout
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto p-8">
        <Outlet key={clientVersion} />
      </main>
    </div>
  );
}
