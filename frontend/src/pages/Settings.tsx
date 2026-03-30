import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import CustomFieldsManager from "../components/settings/CustomFieldsManager";
import {
  fetchRoutingSettings,
  updateRoutingSettings,
  getApiKeys,
  setApiKey,
  deleteApiKey,
  verifyApiKey,
  getAiProvider,
  setAiProvider,
} from "../api/settings";
import {
  listAdminUsers,
  createAdminUser,
  updateAdminUser,
  removeUserFromWorkspace,
  type AdminUser,
} from "../api/admin";
import type { ApiKeyEntry, RoutingSettings } from "../types/settings";
import { useAuth } from "../contexts/AuthContext";

// ── Integration config ──────────────────────────────────────────────────────

interface Integration {
  key: string;
  label: string;
  icon: string;
  iconBg: string;
  isUrl: boolean;
  placeholder: string;
}

const INTEGRATIONS: Integration[] = [
  { key: "anthropic", label: "Anthropic (Claude)", icon: "A", iconBg: "bg-orange-100 text-orange-700", isUrl: false, placeholder: "sk-ant-..." },
  { key: "openai",    label: "OpenAI (GPT)",        icon: "O", iconBg: "bg-emerald-100 text-emerald-700", isUrl: false, placeholder: "sk-..." },
  { key: "apollo",    label: "Apollo",               icon: "P", iconBg: "bg-violet-100 text-violet-700",  isUrl: false, placeholder: "API key" },
  { key: "ghl_inbound",  label: "GoHighLevel Inbound",  icon: "G", iconBg: "bg-blue-100 text-blue-700",  isUrl: true,  placeholder: "https://..." },
  { key: "ghl_outbound", label: "GoHighLevel Outbound", icon: "G", iconBg: "bg-blue-100 text-blue-700",  isUrl: true,  placeholder: "https://..." },
  { key: "clearbit",  label: "Clearbit",             icon: "C", iconBg: "bg-pink-100 text-pink-700",    isUrl: false, placeholder: "API key" },
  { key: "proxycurl", label: "Proxycurl",            icon: "X", iconBg: "bg-teal-100 text-teal-700",   isUrl: false, placeholder: "API key" },
];

const AI_KEYS = new Set(["anthropic", "openai"]);

// ── Types ───────────────────────────────────────────────────────────────────

type CardOp = {
  saving?: boolean;
  saveMsg?: string;        // "Saved" or error text
  saveMsgType?: "ok" | "err";
  verifying?: boolean;
  verifyResult?: "success" | "failed";
  confirmRemove?: boolean;
  removing?: boolean;
};

// ── Component ───────────────────────────────────────────────────────────────

export default function Settings() {
  const { user } = useAuth();
  const navigate = useNavigate();

  // Members do not have access to Settings
  if (user && user.role === "member") {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <p className="text-4xl mb-4">403</p>
        <p className="text-lg font-semibold text-gray-800 mb-1">Access Denied</p>
        <p className="text-sm text-gray-500 mb-6">
          You don't have permission to access Settings.
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

  // ── Existing state (untouched) ──
  const [routing, setRouting] = useState<RoutingSettings>({
    ghl_inbound_webhook_url: "",
    ghl_outbound_webhook_url: "",
    score_inbound_threshold: 70,
    score_outbound_threshold: 40,
  });
  const [routingLoading, setRoutingLoading] = useState(true);
  const [routingSaving, setRoutingSaving] = useState(false);
  const [routingMsg, setRoutingMsg] = useState("");

  // ── New: API Keys & Integrations state ──
  const [keyStatuses, setKeyStatuses] = useState<ApiKeyEntry[]>([]);
  const [keysLoading, setKeysLoading] = useState(true);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [cardOps, setCardOps] = useState<Record<string, CardOp>>({});

  const [aiProvider, setAiProviderState] = useState<{ provider: string; available: string[] } | null>(null);
  const [aiProviderSaving, setAiProviderSaving] = useState(false);
  const [aiProviderMsg, setAiProviderMsg] = useState("");

  // ── Load all data ──
  useEffect(() => {
    fetchRoutingSettings()
      .then((d) => setRouting({
        ghl_inbound_webhook_url: d.ghl_inbound_webhook_url || "",
        ghl_outbound_webhook_url: d.ghl_outbound_webhook_url || "",
        score_inbound_threshold: d.score_inbound_threshold,
        score_outbound_threshold: d.score_outbound_threshold,
      }))
      .catch(() => setRoutingMsg("Failed to load routing settings"))
      .finally(() => setRoutingLoading(false));

    getApiKeys()
      .then(setKeyStatuses)
      .catch(() => {}) // non-fatal
      .finally(() => setKeysLoading(false));

    getAiProvider()
      .then(setAiProviderState)
      .catch(() => {});
  }, []);

  // ── Helpers ──
  const patchCard = (key: string, patch: Partial<CardOp>) =>
    setCardOps((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));

  const statusFor = (keyName: string): ApiKeyEntry =>
    keyStatuses.find((k) => k.key_name === keyName) ?? {
      key_name: keyName,
      is_set: false,
      is_active: false,
      last_verified_at: null,
    };

  // ── Key handlers ──
  const handleSaveKey = async (keyName: string) => {
    const val = (inputs[keyName] ?? "").trim();
    if (!val) return;
    patchCard(keyName, { saving: true, saveMsg: undefined, verifyResult: undefined });
    try {
      const result = await setApiKey(keyName, val);
      // Update status for this card only
      setKeyStatuses((prev) => {
        const exists = prev.some((k) => k.key_name === keyName);
        const updated: ApiKeyEntry = {
          key_name: result.key_name,
          is_set: result.is_set,
          is_active: result.is_active,
          last_verified_at: result.last_verified_at,
        };
        return exists
          ? prev.map((k) => (k.key_name === keyName ? updated : k))
          : [...prev, updated];
      });
      // Refresh AI provider availability
      getAiProvider().then(setAiProviderState).catch(() => {});
      setInputs((prev) => ({ ...prev, [keyName]: "" }));
      patchCard(keyName, {
        saving: false,
        saveMsg: "Saved",
        saveMsgType: "ok",
        // Auto-verify result came back from the save endpoint
        verifyResult: result.verified ? "success" : undefined,
      });
    } catch (err) {
      patchCard(keyName, {
        saving: false,
        saveMsg: err instanceof Error ? err.message : "Save failed",
        saveMsgType: "err",
      });
    }
  };

  const handleVerifyKey = async (keyName: string) => {
    patchCard(keyName, { verifying: true, verifyResult: undefined });
    try {
      const res = await verifyApiKey(keyName);
      setKeyStatuses((prev) =>
        prev.map((k) =>
          k.key_name === keyName ? { ...k, last_verified_at: res.last_verified_at } : k
        )
      );
      patchCard(keyName, { verifying: false, verifyResult: res.verified ? "success" : "failed" });
    } catch {
      patchCard(keyName, { verifying: false, verifyResult: "failed" });
    }
  };

  const handleDeleteKey = async (keyName: string) => {
    patchCard(keyName, { removing: true });
    try {
      await deleteApiKey(keyName);
      setKeyStatuses((prev) =>
        prev.map((k) =>
          k.key_name === keyName
            ? { key_name: keyName, is_set: false, is_active: false, last_verified_at: null }
            : k
        )
      );
      // Refresh AI provider
      getAiProvider().then(setAiProviderState).catch(() => {});
      patchCard(keyName, { removing: false, confirmRemove: false, verifyResult: undefined, saveMsg: undefined });
    } catch {
      patchCard(keyName, { removing: false, saveMsg: "Delete failed", saveMsgType: "err" });
    }
  };

  const handleSetAiProvider = async (provider: string) => {
    setAiProviderSaving(true);
    setAiProviderMsg("");
    try {
      await setAiProvider(provider);
      setAiProviderState((prev) => prev ? { ...prev, provider } : null);
      setAiProviderMsg(`Active provider set to ${provider === "anthropic" ? "Claude (Anthropic)" : "GPT (OpenAI)"}`);
    } catch (err) {
      setAiProviderMsg(err instanceof Error ? err.message : "Failed to set provider");
    } finally {
      setAiProviderSaving(false);
    }
  };

  // ── Existing handlers (untouched) ──
  const saveRouting = async () => {
    setRoutingSaving(true);
    setRoutingMsg("");
    try {
      await updateRoutingSettings({
        ghl_inbound_webhook_url: routing.ghl_inbound_webhook_url || null,
        ghl_outbound_webhook_url: routing.ghl_outbound_webhook_url || null,
        score_inbound_threshold: routing.score_inbound_threshold,
        score_outbound_threshold: routing.score_outbound_threshold,
      });
      setRoutingMsg("Routing settings saved");
    } catch {
      setRoutingMsg("Failed to save routing settings");
    } finally {
      setRoutingSaving(false);
    }
  };

  // ── Card sub-components ──
  const StatusBadge = ({ entry, verifyResult }: { entry: ApiKeyEntry; verifyResult?: "success" | "failed" }) => {
    if (verifyResult === "failed") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
          Verification failed
        </span>
      );
    }
    if (!entry.is_set) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
          Not configured
        </span>
      );
    }
    if (verifyResult === "success" || entry.last_verified_at) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
          <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
          Connected
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-700">
        Configured
      </span>
    );
  };

  const renderCard = (integration: Integration) => {
    const entry = statusFor(integration.key);
    const op = cardOps[integration.key] ?? {};
    const inputVal = inputs[integration.key] ?? "";

    return (
      <div key={integration.key} className="rounded-lg border border-gray-200 bg-white p-4">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-bold ${integration.iconBg}`}>
              {integration.icon}
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-900">{integration.label}</p>
              {entry.last_verified_at && (
                <p className="text-xs text-gray-400">
                  Verified {new Date(entry.last_verified_at).toLocaleDateString()}
                </p>
              )}
            </div>
          </div>
          <StatusBadge entry={entry} verifyResult={op.verifyResult} />
        </div>

        {/* Input row */}
        <div className="mt-3 flex gap-2">
          <input
            type="password"
            value={inputVal}
            onChange={(e) => setInputs((prev) => ({ ...prev, [integration.key]: e.target.value }))}
            placeholder={entry.is_set ? `Enter new ${integration.isUrl ? "URL" : "API key"} to replace…` : integration.placeholder}
            className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm font-mono focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            onKeyDown={(e) => { if (e.key === "Enter") handleSaveKey(integration.key); }}
          />
          <button
            onClick={() => handleSaveKey(integration.key)}
            disabled={op.saving || !inputVal.trim()}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {op.saving ? "Saving…" : "Save"}
          </button>
        </div>

        {/* Action row */}
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {/* Verify button — only for API keys, not URLs */}
            {!integration.isUrl && entry.is_set && (
              <button
                onClick={() => handleVerifyKey(integration.key)}
                disabled={op.verifying}
                className="rounded-md border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
              >
                {op.verifying ? (
                  <span className="flex items-center gap-1">
                    <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                    Verifying…
                  </span>
                ) : op.verifyResult === "success" ? (
                  "Valid ✓"
                ) : op.verifyResult === "failed" ? (
                  "Invalid ✗"
                ) : (
                  "Verify"
                )}
              </button>
            )}

            {/* Remove button — only shown when key is set */}
            {entry.is_set && !op.confirmRemove && (
              <button
                onClick={() => patchCard(integration.key, { confirmRemove: true })}
                className="rounded-md border border-red-200 px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50"
              >
                Remove
              </button>
            )}

            {/* Confirmation */}
            {op.confirmRemove && (
              <span className="flex items-center gap-2">
                <span className="text-xs text-gray-600">Remove this integration?</span>
                <button
                  onClick={() => handleDeleteKey(integration.key)}
                  disabled={op.removing}
                  className="rounded-md bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
                >
                  {op.removing ? "Removing…" : "Yes, remove"}
                </button>
                <button
                  onClick={() => patchCard(integration.key, { confirmRemove: false })}
                  className="rounded-md border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50"
                >
                  Cancel
                </button>
              </span>
            )}
          </div>

          {/* Save feedback */}
          {op.saveMsg && (
            <span className={`text-xs font-medium ${op.saveMsgType === "ok" ? "text-green-600" : "text-red-600"}`}>
              {op.saveMsg}
            </span>
          )}
        </div>
      </div>
    );
  };

  // ── AI Provider Selector ──
  const renderAiProviderSelector = () => {
    if (!aiProvider) return null;
    const providers = [
      { id: "anthropic", label: "Claude (Anthropic)" },
      { id: "openai",    label: "GPT (OpenAI)" },
    ];
    return (
      <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 p-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-indigo-700">
          Active AI Provider
        </p>
        <div className="flex items-center gap-2">
          {providers.map(({ id, label }) => {
            const available = aiProvider.available.includes(id);
            const active = aiProvider.provider === id;
            return (
              <button
                key={id}
                onClick={() => available && !active && handleSetAiProvider(id)}
                disabled={!available || aiProviderSaving || active}
                title={!available ? `Add a ${label} API key first` : undefined}
                className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-indigo-600 text-white"
                    : available
                    ? "border border-indigo-300 bg-white text-indigo-700 hover:bg-indigo-50"
                    : "cursor-not-allowed border border-gray-200 bg-white text-gray-400"
                }`}
              >
                {label}
              </button>
            );
          })}
          {aiProviderSaving && (
            <span className="text-xs text-indigo-500">Saving…</span>
          )}
          {aiProviderMsg && !aiProviderSaving && (
            <span className={`text-xs font-medium ${aiProviderMsg.toLowerCase().includes("fail") ? "text-red-600" : "text-indigo-700"}`}>
              {aiProviderMsg}
            </span>
          )}
        </div>
      </div>
    );
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 max-w-4xl">
      <h1 className="text-2xl font-bold text-gray-900">Settings</h1>

      {/* ── API Keys & Integrations (FIRST) ── */}
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <div className="mb-4">
          <h2 className="text-lg font-semibold text-gray-900">API Keys &amp; Integrations</h2>
          <p className="mt-0.5 text-xs text-gray-500">
            Keys are encrypted at rest and never returned by the API. Leave blank to keep the current value.
          </p>
        </div>

        {keysLoading ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : (
          <div className="space-y-3">
            {/* AI provider cards */}
            {INTEGRATIONS.filter((i) => AI_KEYS.has(i.key)).map(renderCard)}

            {/* AI Provider Selector (between AI cards and other cards) */}
            {renderAiProviderSelector()}

            {/* All other integration cards */}
            {INTEGRATIONS.filter((i) => !AI_KEYS.has(i.key)).map(renderCard)}
          </div>
        )}
      </div>

      {/* ── Routing Thresholds ── */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-1">Routing Thresholds</h2>
        <p className="mt-0.5 mb-4 text-xs text-gray-500">
          GHL webhook URLs are managed above in API Keys &amp; Integrations.
        </p>
        {routingLoading ? (
          <p className="text-gray-500 text-sm">Loading...</p>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Inbound Threshold</label>
                <input
                  type="number"
                  value={routing.score_inbound_threshold}
                  onChange={(e) => setRouting({ ...routing, score_inbound_threshold: Number(e.target.value) })}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Outbound Threshold</label>
                <input
                  type="number"
                  value={routing.score_outbound_threshold}
                  onChange={(e) => setRouting({ ...routing, score_outbound_threshold: Number(e.target.value) })}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            </div>
            {routingMsg && (
              <p className={`text-sm ${routingMsg.includes("Failed") ? "text-red-600" : "text-green-600"}`}>
                {routingMsg}
              </p>
            )}
            <button
              onClick={saveRouting}
              disabled={routingSaving}
              className="px-4 py-2 text-sm text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
            >
              {routingSaving ? "Saving..." : "Save Thresholds"}
            </button>
          </div>
        )}
      </div>
      {/* ── Custom Fields ── */}
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <div className="mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Custom Fields</h2>
          <p className="mt-0.5 text-xs text-gray-500">
            Define custom data fields for leads and companies.
          </p>
        </div>
        <CustomFieldsManager />
      </div>

      {/* ── Team ── */}
      <TeamSection currentClientId={user?.active_client_id ?? null} />
    </div>
  );
}

// ── Team section ──────────────────────────────────────────────────────────────

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

function InviteUserModal({
  clientId,
  onCreated,
  onClose,
}: {
  clientId: number;
  onCreated: () => void;
  onClose: () => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "member">("member");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (!email.trim() || !password.trim()) { setError("Email and password are required"); return; }
    if (password.length < 8) { setError("Password must be at least 8 characters"); return; }
    setSaving(true);
    setError(null);
    try {
      await createAdminUser(email.trim(), password, role, name.trim() || undefined, [clientId]);
      onCreated();
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
            <h3 className="text-base font-semibold text-gray-900">Invite User</h3>
            <button onClick={onClose} className="text-xl leading-none text-gray-400 hover:text-gray-600">&times;</button>
          </div>
          <div className="space-y-4 px-5 py-4">
            {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Full Name</label>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Smith"
                // eslint-disable-next-line jsx-a11y/no-autofocus
                autoFocus
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Email <span className="text-red-500">*</span></label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jane@example.com"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Password <span className="text-red-500">*</span></label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Min 8 characters"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Role</label>
              <select value={role} onChange={(e) => setRole(e.target.value as "admin" | "member")}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500">
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t px-5 py-4">
            <button onClick={onClose} className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Cancel</button>
            <button onClick={handleSubmit} disabled={saving} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
              {saving ? "Inviting…" : "Invite User"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function TeamSection({ currentClientId }: { currentClientId: number | null }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [roleSaving, setRoleSaving] = useState<Record<number, boolean>>({});
  const [removing, setRemoving] = useState<Record<number, boolean>>({});
  const { user: currentUser } = useAuth();

  const load = () => {
    setLoading(true);
    listAdminUsers()
      .then(setUsers)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleRoleChange(u: AdminUser, newRole: string) {
    setRoleSaving((p) => ({ ...p, [u.id]: true }));
    try {
      await updateAdminUser(u.id, { role: newRole });
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update role");
    } finally {
      setRoleSaving((p) => ({ ...p, [u.id]: false }));
    }
  }

  async function handleRemove(u: AdminUser) {
    if (!currentClientId) return;
    if (!confirm(`Remove ${u.name ?? u.email} from this workspace?`)) return;
    setRemoving((p) => ({ ...p, [u.id]: true }));
    try {
      await removeUserFromWorkspace(u.id, currentClientId);
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to remove user");
    } finally {
      setRemoving((p) => ({ ...p, [u.id]: false }));
    }
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Team</h2>
          <p className="mt-0.5 text-xs text-gray-500">Users in this workspace.</p>
        </div>
        {currentClientId && (
          <button
            onClick={() => setShowInvite(true)}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Invite User
          </button>
        )}
      </div>

      {loading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-100">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                <th className="px-4 py-2.5">Name</th>
                <th className="px-4 py-2.5">Email</th>
                <th className="px-4 py-2.5">Role</th>
                <th className="px-4 py-2.5">Last Login</th>
                <th className="px-4 py-2.5">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {users.map((u) => {
                const isSelf = u.id === currentUser?.id;
                const isSuperadmin = u.role === "superadmin";
                return (
                  <tr key={u.id} className="text-gray-700">
                    <td className="px-4 py-2.5 font-medium">
                      {u.name ?? <span className="text-gray-400 italic">—</span>}
                    </td>
                    <td className="px-4 py-2.5 text-gray-500">{u.email}</td>
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
                    <td className="px-4 py-2.5 text-gray-400">
                      {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : "Never"}
                    </td>
                    <td className="px-4 py-2.5">
                      {!isSelf && !isSuperadmin && (
                        <button
                          onClick={() => handleRemove(u)}
                          disabled={removing[u.id]}
                          className="text-xs font-medium text-red-500 hover:text-red-700 disabled:opacity-50"
                        >
                          {removing[u.id] ? "Removing…" : "Remove"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {users.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-gray-400">No users in this workspace.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showInvite && currentClientId && (
        <InviteUserModal
          clientId={currentClientId}
          onCreated={load}
          onClose={() => setShowInvite(false)}
        />
      )}
    </div>
  );
}
