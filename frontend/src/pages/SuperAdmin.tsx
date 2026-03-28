import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  listAdminClients,
  listAdminUsers,
  updateUserRole,
  createAdminUser,
  type AdminClient,
  type AdminUser,
} from "../api/admin";
import { useAuth } from "../contexts/AuthContext";

const ROLES = ["member", "admin", "superadmin"] as const;

export default function SuperAdmin() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [clients, setClients] = useState<AdminClient[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Invite form
  const [inviteEmail, setInviteEmail] = useState("");
  const [invitePassword, setInvitePassword] = useState("");
  const [inviteRole, setInviteRole] = useState<string>("member");
  const [inviting, setInviting] = useState(false);
  const [inviteMsg, setInviteMsg] = useState("");

  // Role update state: userId → new role being saved
  const [updatingRole, setUpdatingRole] = useState<Record<number, boolean>>({});

  if (user && user.role !== "superadmin") {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <p className="text-4xl mb-4">403</p>
        <p className="text-lg font-semibold text-gray-800 mb-1">Access Denied</p>
        <p className="text-sm text-gray-500 mb-6">
          Super Admin access is restricted to superadmins only.
        </p>
        <button
          onClick={() => navigate("/")}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          Go to Dashboard
        </button>
      </div>
    );
  }

  useEffect(() => {
    Promise.all([listAdminClients(), listAdminUsers()])
      .then(([c, u]) => {
        setClients(c);
        setUsers(u);
      })
      .catch(() => setError("Failed to load super admin data"))
      .finally(() => setLoading(false));
  }, []);

  async function handleRoleChange(userId: number, newRole: string) {
    setUpdatingRole((prev) => ({ ...prev, [userId]: true }));
    try {
      const updated = await updateUserRole(userId, newRole);
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update role");
    } finally {
      setUpdatingRole((prev) => ({ ...prev, [userId]: false }));
    }
  }

  async function handleInvite() {
    if (!inviteEmail.trim() || !invitePassword.trim()) return;
    setInviting(true);
    setInviteMsg("");
    try {
      const created = await createAdminUser(inviteEmail.trim(), invitePassword.trim(), inviteRole);
      setUsers((prev) => [...prev, created]);
      setInviteEmail("");
      setInvitePassword("");
      setInviteRole("member");
      setInviteMsg(`Created user ${created.email}`);
    } catch (err) {
      setInviteMsg(err instanceof Error ? err.message : "Failed to create user");
    } finally {
      setInviting(false);
    }
  }

  if (loading) return <div className="text-gray-500 py-8">Loading…</div>;
  if (error) return <div className="text-red-600 py-8">{error}</div>;

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Super Admin</h1>
        <p className="mt-1 text-sm text-gray-500">Platform-level administration.</p>
      </div>

      {/* ── Clients ── */}
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Workspaces
          <span className="ml-2 text-sm font-normal text-gray-400">({clients.length})</span>
        </h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="pb-2 pr-4">Name</th>
              <th className="pb-2 pr-4">Users</th>
              <th className="pb-2">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {clients.map((c) => (
              <tr key={c.id} className="text-gray-700">
                <td className="py-2 pr-4 font-medium">{c.name}</td>
                <td className="py-2 pr-4 text-gray-500">{c.user_count}</td>
                <td className="py-2 text-gray-400">
                  {new Date(c.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
            {clients.length === 0 && (
              <tr>
                <td colSpan={3} className="py-4 text-center text-gray-400">
                  No workspaces yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── Users ── */}
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          All Users
          <span className="ml-2 text-sm font-normal text-gray-400">({users.length})</span>
        </h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="pb-2 pr-4">Email</th>
              <th className="pb-2 pr-4">Role</th>
              <th className="pb-2 pr-4">Active</th>
              <th className="pb-2">Joined</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {users.map((u) => (
              <tr key={u.id} className="text-gray-700">
                <td className="py-2 pr-4">{u.email}</td>
                <td className="py-2 pr-4">
                  <select
                    value={u.role}
                    disabled={updatingRole[u.id]}
                    onChange={(e) => handleRoleChange(u.id, e.target.value)}
                    className="rounded border border-gray-300 px-2 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </td>
                <td className="py-2 pr-4">
                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${u.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                    {u.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="py-2 text-gray-400">
                  {new Date(u.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={4} className="py-4 text-center text-gray-400">
                  No users yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── Invite user ── */}
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Create User</h2>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
            <input
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="user@example.com"
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 w-56"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Password</label>
            <input
              type="password"
              value={invitePassword}
              onChange={(e) => setInvitePassword(e.target.value)}
              placeholder="temporary password"
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 w-44"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Role</label>
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          <button
            onClick={handleInvite}
            disabled={inviting || !inviteEmail.trim() || !invitePassword.trim()}
            className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {inviting ? "Creating…" : "Create"}
          </button>
          {inviteMsg && (
            <span className={`text-xs font-medium ${inviteMsg.toLowerCase().includes("fail") || inviteMsg.toLowerCase().includes("error") ? "text-red-600" : "text-green-600"}`}>
              {inviteMsg}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
