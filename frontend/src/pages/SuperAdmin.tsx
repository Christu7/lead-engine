import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  listAdminClients,
  listAdminUsers,
  createAdminUser,
  updateAdminUser,
  assignUserToWorkspace,
  removeUserFromWorkspace,
  updateAdminClient,
  deleteAdminClient,
  resetUserPassword,
  type AdminClient,
  type AdminUser,
} from "../api/admin";
import { createClient } from "../api/client";
import { useAuth } from "../contexts/AuthContext";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleDateString();
}

function RoleBadge({ role }: { role: string }) {
  const styles: Record<string, string> = {
    superadmin: "bg-purple-100 text-purple-700",
    admin: "bg-blue-100 text-blue-700",
    member: "bg-gray-100 text-gray-600",
  };
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${styles[role] ?? styles.member}`}>
      {role}
    </span>
  );
}

// ── Add User Modal ─────────────────────────────────────────────────────────────

function AddUserModal({
  clients,
  onCreated,
  onClose,
}: {
  clients: AdminClient[];
  onCreated: (user: AdminUser) => void;
  onClose: () => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "member">("member");
  const [selectedClientIds, setSelectedClientIds] = useState<Set<number>>(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeClients = clients.filter((c) => c.is_active);

  function toggleClient(id: number) {
    setSelectedClientIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSubmit() {
    if (!email.trim() || !password.trim()) {
      setError("Email and password are required");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const user = await createAdminUser(
        email.trim(),
        password,
        role,
        name.trim() || undefined,
        [...selectedClientIds],
      );
      onCreated(user);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create user");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-md rounded-lg bg-white shadow-xl">
          <div className="flex items-center justify-between border-b px-5 py-4">
            <h3 className="text-base font-semibold text-gray-900">Add User</h3>
            <button onClick={onClose} className="text-xl leading-none text-gray-400 hover:text-gray-600">&times;</button>
          </div>

          <div className="space-y-4 px-5 py-4">
            {error && (
              <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
            )}

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Full Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Jane Smith"
                // eslint-disable-next-line jsx-a11y/no-autofocus
                autoFocus
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Email <span className="text-red-500">*</span>
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="jane@example.com"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Password <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Min 8 characters"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Role</label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as "admin" | "member")}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
            </div>

            {activeClients.length > 0 && (
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700">
                  Workspaces
                </label>
                <div className="max-h-40 space-y-1.5 overflow-y-auto rounded-md border border-gray-200 p-2">
                  {activeClients.map((c) => (
                    <label key={c.id} className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 hover:bg-gray-50">
                      <input
                        type="checkbox"
                        checked={selectedClientIds.has(c.id)}
                        onChange={() => toggleClient(c.id)}
                        className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span className="text-sm text-gray-700">{c.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="flex justify-end gap-2 border-t px-5 py-4">
            <button
              onClick={onClose}
              className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={saving}
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? "Creating…" : "Create User"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ── Manage Workspaces Modal ────────────────────────────────────────────────────

function ManageWorkspacesModal({
  user,
  allClients,
  onClose,
  onRefresh,
}: {
  user: AdminUser;
  allClients: AdminClient[];
  onClose: () => void;
  onRefresh: () => void;
}) {
  const [localClients, setLocalClients] = useState(user.clients);
  const [addClientId, setAddClientId] = useState<number | "">("");
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const assignedIds = new Set(localClients.map((c) => c.id));
  const available = allClients.filter((c) => c.is_active && !assignedIds.has(c.id));

  async function handleAdd() {
    if (!addClientId) return;
    setAdding(true);
    setError(null);
    try {
      await assignUserToWorkspace(user.id, Number(addClientId));
      const added = allClients.find((c) => c.id === Number(addClientId))!;
      setLocalClients((prev) => [...prev, { id: added.id, name: added.name }]);
      setAddClientId("");
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add workspace");
    } finally {
      setAdding(false);
    }
  }

  async function handleRemove(clientId: number) {
    if (localClients.length <= 1) {
      setError("Cannot remove user from their only workspace");
      return;
    }
    setRemoving(clientId);
    setError(null);
    try {
      await removeUserFromWorkspace(user.id, clientId);
      setLocalClients((prev) => prev.filter((c) => c.id !== clientId));
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove workspace");
    } finally {
      setRemoving(null);
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-sm rounded-lg bg-white shadow-xl">
          <div className="flex items-center justify-between border-b px-5 py-4">
            <div>
              <h3 className="text-base font-semibold text-gray-900">Manage Workspaces</h3>
              <p className="text-xs text-gray-500 mt-0.5">{user.name ?? user.email}</p>
            </div>
            <button onClick={onClose} className="text-xl leading-none text-gray-400 hover:text-gray-600">&times;</button>
          </div>

          <div className="px-5 py-4 space-y-4">
            {error && (
              <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
            )}

            {/* Current workspaces */}
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500 mb-2">
                Current workspaces ({localClients.length})
              </p>
              <div className="space-y-1">
                {localClients.map((c) => (
                  <div key={c.id} className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2">
                    <span className="text-sm text-gray-800">{c.name}</span>
                    <button
                      onClick={() => handleRemove(c.id)}
                      disabled={removing === c.id || localClients.length <= 1}
                      title={localClients.length <= 1 ? "Cannot remove last workspace" : "Remove"}
                      className="text-gray-400 hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      {removing === c.id ? (
                        <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                        </svg>
                      ) : (
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      )}
                    </button>
                  </div>
                ))}
                {localClients.length === 0 && (
                  <p className="text-sm text-gray-400 italic">No workspaces assigned</p>
                )}
              </div>
            </div>

            {/* Add to workspace */}
            {available.length > 0 && (
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500 mb-2">Add to workspace</p>
                <div className="flex gap-2">
                  <select
                    value={addClientId}
                    onChange={(e) => setAddClientId(e.target.value === "" ? "" : Number(e.target.value))}
                    className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="">Select workspace…</option>
                    {available.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                  <button
                    onClick={handleAdd}
                    disabled={!addClientId || adding}
                    className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {adding ? "…" : "Add"}
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="flex justify-end border-t px-5 py-4">
            <button
              onClick={onClose}
              className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ── Reset Password Modal ───────────────────────────────────────────────────────

function ResetPasswordModal({
  user,
  onClose,
}: {
  user: AdminUser;
  onClose: () => void;
}) {
  const [newPassword, setNewPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ text: string; type: "ok" | "err" } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (newPassword.length < 8) {
      setMsg({ text: "Password must be at least 8 characters", type: "err" });
      return;
    }
    setSaving(true);
    try {
      await resetUserPassword(user.id, newPassword);
      setMsg({ text: "Password reset", type: "ok" });
      setNewPassword("");
    } catch (err) {
      setMsg({ text: err instanceof Error ? err.message : "Failed to reset password", type: "err" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-sm rounded-lg bg-white shadow-xl">
          <div className="flex items-center justify-between border-b px-5 py-4">
            <div>
              <h3 className="text-base font-semibold text-gray-900">Reset Password</h3>
              <p className="text-xs text-gray-500 mt-0.5">{user.name ?? user.email}</p>
            </div>
            <button onClick={onClose} className="text-xl leading-none text-gray-400 hover:text-gray-600">&times;</button>
          </div>
          <form onSubmit={handleSubmit}>
            <div className="px-5 py-4 space-y-4">
              {msg && (
                <p className={`rounded-md px-3 py-2 text-sm ${msg.type === "ok" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}>
                  {msg.text}
                </p>
              )}
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  New Password <span className="text-red-500">*</span>
                </label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Min 8 characters"
                  // eslint-disable-next-line jsx-a11y/no-autofocus
                  autoFocus
                  required
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <p className="text-xs text-gray-400">
                No current password required. The user's existing sessions will be invalidated.
              </p>
            </div>
            <div className="flex justify-end gap-2 border-t px-5 py-4">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {saving ? "Resetting…" : "Reset Password"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}

// ── Users tab ──────────────────────────────────────────────────────────────────

function UsersTab({
  users,
  clients,
  currentUserId,
  onRefresh,
}: {
  users: AdminUser[];
  clients: AdminClient[];
  currentUserId: number;
  onRefresh: () => void;
}) {
  const [showAddUser, setShowAddUser] = useState(false);
  const [wsUser, setWsUser] = useState<AdminUser | null>(null);
  const [resetPwUser, setResetPwUser] = useState<AdminUser | null>(null);
  const [roleSaving, setRoleSaving] = useState<Record<number, boolean>>({});
  const [activeSaving, setActiveSaving] = useState<Record<number, boolean>>({});

  async function handleRoleChange(u: AdminUser, newRole: string) {
    setRoleSaving((p) => ({ ...p, [u.id]: true }));
    try {
      await updateAdminUser(u.id, { role: newRole });
      onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update role");
    } finally {
      setRoleSaving((p) => ({ ...p, [u.id]: false }));
    }
  }

  async function handleToggleActive(u: AdminUser) {
    setActiveSaving((p) => ({ ...p, [u.id]: true }));
    try {
      await updateAdminUser(u.id, { is_active: !u.is_active });
      onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update status");
    } finally {
      setActiveSaving((p) => ({ ...p, [u.id]: false }));
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {users.length} user{users.length !== 1 ? "s" : ""}
        </p>
        <button
          onClick={() => setShowAddUser(true)}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
        >
          Add User
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="px-4 py-2.5">Name</th>
              <th className="px-4 py-2.5">Email</th>
              <th className="px-4 py-2.5">Role</th>
              <th className="px-4 py-2.5">Workspaces</th>
              <th className="px-4 py-2.5">Status</th>
              <th className="px-4 py-2.5">Last Login</th>
              <th className="px-4 py-2.5">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {users.map((u) => {
              const isSelf = u.id === currentUserId;
              const isSuperadmin = u.role === "superadmin";
              return (
                <tr key={u.id} className={`text-gray-700 ${!u.is_active ? "opacity-60" : ""}`}>
                  <td className="px-4 py-2.5 font-medium">
                    {u.name ?? <span className="text-gray-400 italic">—</span>}
                  </td>
                  <td className="px-4 py-2.5 text-gray-500">{u.email}</td>

                  {/* Role cell */}
                  <td className="px-4 py-2.5">
                    {isSuperadmin || isSelf ? (
                      <RoleBadge role={u.role} />
                    ) : (
                      <select
                        value={u.role}
                        disabled={roleSaving[u.id]}
                        onChange={(e) => handleRoleChange(u, e.target.value)}
                        className="rounded border border-gray-200 px-2 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
                      >
                        <option value="member">Member</option>
                        <option value="admin">Admin</option>
                      </select>
                    )}
                  </td>

                  {/* Workspaces */}
                  <td className="px-4 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {u.clients.map((c) => (
                        <span
                          key={c.id}
                          className="inline-flex rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700"
                        >
                          {c.name}
                        </span>
                      ))}
                      {u.clients.length === 0 && (
                        <span className="text-xs text-gray-400 italic">None</span>
                      )}
                    </div>
                  </td>

                  {/* Active toggle */}
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => !isSelf && handleToggleActive(u)}
                      disabled={isSelf || activeSaving[u.id]}
                      title={isSelf ? "Cannot deactivate your own account" : u.is_active ? "Deactivate" : "Activate"}
                      className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 ${
                        u.is_active ? "bg-indigo-600" : "bg-gray-200"
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                          u.is_active ? "translate-x-4" : "translate-x-0"
                        }`}
                      />
                    </button>
                  </td>

                  <td className="px-4 py-2.5 text-gray-400">{fmtDate(u.last_login_at)}</td>

                  {/* Actions */}
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setWsUser(u)}
                        className="rounded-md border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 hover:text-indigo-600"
                      >
                        Workspaces
                      </button>
                      <button
                        onClick={() => setResetPwUser(u)}
                        className="rounded-md border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 hover:text-indigo-600"
                      >
                        Reset Password
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {users.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-gray-400">
                  No users yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showAddUser && (
        <AddUserModal
          clients={clients}
          onCreated={(_user) => { onRefresh(); }}
          onClose={() => setShowAddUser(false)}
        />
      )}

      {wsUser && (
        <ManageWorkspacesModal
          user={wsUser}
          allClients={clients}
          onClose={() => setWsUser(null)}
          onRefresh={onRefresh}
        />
      )}

      {resetPwUser && (
        <ResetPasswordModal
          user={resetPwUser}
          onClose={() => setResetPwUser(null)}
        />
      )}
    </div>
  );
}

// ── Workspaces tab ────────────────────────────────────────────────────────────

function WorkspacesTab({ clients, onRefresh }: { clients: AdminClient[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const nameInputRef = useRef<HTMLInputElement>(null);

  const startEdit = (c: AdminClient) => {
    setEditingId(c.id);
    setEditName(c.name);
    setEditDescription(c.description ?? "");
    setEditError(null);
    setTimeout(() => nameInputRef.current?.focus(), 0);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditError(null);
  };

  const saveEdit = async (clientId: number) => {
    const name = editName.trim();
    if (!name) { setEditError("Name is required"); return; }
    setEditSaving(true);
    setEditError(null);
    try {
      await updateAdminClient(clientId, {
        name,
        description: editDescription.trim() || null,
      });
      setEditingId(null);
      onRefresh();
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setEditSaving(false);
    }
  };

  const confirmDelete = async () => {
    if (!confirmDeleteId) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteAdminClient(confirmDeleteId);
      setConfirmDeleteId(null);
      onRefresh();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  const handleCreate = async () => {
    const name = createName.trim();
    if (!name) { setCreateError("Name is required"); return; }
    setCreating(true);
    setCreateError(null);
    try {
      await createClient(name);
      setShowCreate(false);
      setCreateName("");
      setCreateDescription("");
      onRefresh();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  };

  const deleteTarget = clients.find((c) => c.id === confirmDeleteId);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {clients.length} workspace{clients.length !== 1 ? "s" : ""}
          <span className="ml-2 text-gray-400">
            ({clients.filter((c) => c.is_active).length} active)
          </span>
        </p>
        <button
          onClick={() => { setShowCreate(true); setCreateError(null); }}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
        >
          Create Workspace
        </button>
      </div>

      {/* Create modal */}
      {showCreate && (
        <>
          <div className="fixed inset-0 z-40 bg-black/30" onClick={() => setShowCreate(false)} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="w-full max-w-sm rounded-lg bg-white shadow-xl">
              <div className="flex items-center justify-between border-b px-5 py-4">
                <h3 className="text-base font-semibold text-gray-900">Create Workspace</h3>
                <button onClick={() => setShowCreate(false)} className="text-xl leading-none text-gray-400 hover:text-gray-600">&times;</button>
              </div>
              <div className="space-y-4 px-5 py-4">
                {createError && (
                  <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{createError}</p>
                )}
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">
                    Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={createName}
                    onChange={(e) => setCreateName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); if (e.key === "Escape") setShowCreate(false); }}
                    placeholder="Acme Corp"
                    // eslint-disable-next-line jsx-a11y/no-autofocus
                    autoFocus
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Description</label>
                  <textarea
                    value={createDescription}
                    onChange={(e) => setCreateDescription(e.target.value)}
                    placeholder="Optional description…"
                    rows={2}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 border-t px-5 py-4">
                <button
                  onClick={() => setShowCreate(false)}
                  className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={creating || !createName.trim()}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {creating ? "Creating…" : "Create"}
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Delete confirmation modal */}
      {confirmDeleteId !== null && deleteTarget && (
        <>
          <div className="fixed inset-0 z-40 bg-black/30" onClick={() => { setConfirmDeleteId(null); setDeleteError(null); }} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="w-full max-w-sm rounded-lg bg-white shadow-xl">
              <div className="border-b px-5 py-4">
                <h3 className="text-base font-semibold text-gray-900">Delete Workspace</h3>
              </div>
              <div className="px-5 py-4">
                {deleteError && (
                  <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{deleteError}</p>
                )}
                <p className="text-sm text-gray-700">
                  Delete <span className="font-semibold">{deleteTarget.name}</span>? This will remove
                  access for <span className="font-semibold">{deleteTarget.user_count}</span>{" "}
                  {deleteTarget.user_count === 1 ? "user" : "users"}.
                  Leads and company data will be preserved.
                </p>
              </div>
              <div className="flex justify-end gap-2 border-t px-5 py-4">
                <button
                  onClick={() => { setConfirmDeleteId(null); setDeleteError(null); }}
                  className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmDelete}
                  disabled={deleting}
                  className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                >
                  {deleting ? "Deleting…" : "Delete Workspace"}
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="px-4 py-2.5">Name</th>
              <th className="px-4 py-2.5">Description</th>
              <th className="px-4 py-2.5 text-right">Users</th>
              <th className="px-4 py-2.5 text-right">Leads</th>
              <th className="px-4 py-2.5 text-right">Companies</th>
              <th className="px-4 py-2.5">Created</th>
              <th className="px-4 py-2.5">Status</th>
              <th className="px-4 py-2.5">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {clients.map((c) => (
              <tr key={c.id} className={`text-gray-700 ${!c.is_active ? "opacity-50" : ""}`}>
                <td className="px-4 py-2.5 font-medium">
                  {editingId === c.id ? (
                    <div className="flex flex-col gap-1">
                      <input
                        ref={nameInputRef}
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") saveEdit(c.id);
                          if (e.key === "Escape") cancelEdit();
                        }}
                        className="w-full max-w-[180px] rounded-md border border-indigo-400 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      />
                      {editError && (
                        <p className="text-xs text-red-500">{editError}</p>
                      )}
                    </div>
                  ) : (
                    c.name
                  )}
                </td>

                <td className="px-4 py-2.5 text-gray-500 max-w-[200px]">
                  {editingId === c.id ? (
                    <input
                      type="text"
                      value={editDescription}
                      onChange={(e) => setEditDescription(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveEdit(c.id);
                        if (e.key === "Escape") cancelEdit();
                      }}
                      placeholder="Description…"
                      className="w-full rounded-md border border-indigo-400 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  ) : (
                    <span className="truncate block">{c.description ?? <span className="text-gray-300">—</span>}</span>
                  )}
                </td>

                <td className="px-4 py-2.5 text-right tabular-nums text-gray-500">{c.user_count}</td>
                <td className="px-4 py-2.5 text-right tabular-nums text-gray-500">{c.lead_count}</td>
                <td className="px-4 py-2.5 text-right tabular-nums text-gray-500">{c.company_count}</td>
                <td className="px-4 py-2.5 text-gray-400">{new Date(c.created_at).toLocaleDateString()}</td>

                <td className="px-4 py-2.5">
                  <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                    c.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"
                  }`}>
                    {c.is_active ? "Active" : "Inactive"}
                  </span>
                </td>

                <td className="px-4 py-2.5">
                  {editingId === c.id ? (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => saveEdit(c.id)}
                        disabled={editSaving}
                        className="text-xs font-medium text-indigo-600 hover:text-indigo-800 disabled:opacity-50"
                      >
                        {editSaving ? "Saving…" : "Save"}
                      </button>
                      <button
                        onClick={cancelEdit}
                        className="text-xs font-medium text-gray-400 hover:text-gray-600"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-3">
                      {c.is_active && (
                        <>
                          <button
                            onClick={() => startEdit(c)}
                            title="Edit workspace"
                            className="text-gray-400 hover:text-indigo-600"
                          >
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536M9 13l6.586-6.586a2 2 0 112.828 2.828L11.828 15.828a2 2 0 01-1.414.586H7v-3.414a2 2 0 01.586-1.414z" />
                            </svg>
                          </button>
                          <button
                            onClick={() => { setConfirmDeleteId(c.id); setDeleteError(null); }}
                            title="Delete workspace"
                            className="text-gray-400 hover:text-red-600"
                          >
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7h6m2 0a2 2 0 00-2-2H9a2 2 0 00-2 2m12 0H5" />
                            </svg>
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {clients.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-gray-400">
                  No workspaces yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function SuperAdmin() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [tab, setTab] = useState<"workspaces" | "users">("workspaces");
  const [clients, setClients] = useState<AdminClient[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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

  const loadData = () => {
    setLoading(true);
    Promise.all([listAdminClients(), listAdminUsers()])
      .then(([c, u]) => { setClients(c); setUsers(u); })
      .catch(() => setError("Failed to load super admin data"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadData(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <div className="text-gray-500 py-8">Loading…</div>;
  if (error) return <div className="text-red-600 py-8">{error}</div>;

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Super Admin</h1>
        <p className="mt-1 text-sm text-gray-500">Platform-level administration.</p>
      </div>

      {/* Tab bar */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex gap-4">
          {(["workspaces", "users"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`pb-3 px-1 text-sm font-medium border-b-2 capitalize transition-colors ${
                tab === t
                  ? "border-indigo-600 text-indigo-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t === "workspaces" ? `Workspaces (${clients.length})` : `Users (${users.length})`}
            </button>
          ))}
        </nav>
      </div>

      {tab === "workspaces" && (
        <WorkspacesTab clients={clients} onRefresh={loadData} />
      )}

      {tab === "users" && user && (
        <UsersTab
          users={users}
          clients={clients}
          currentUserId={user.id}
          onRefresh={loadData}
        />
      )}
    </div>
  );
}
