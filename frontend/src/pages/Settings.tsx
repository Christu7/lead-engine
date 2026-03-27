import { useEffect, useState } from "react";
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
import type { ApiKeyEntry, RoutingSettings } from "../types/settings";

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
    <div className="space-y-6 max-w-2xl">
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
    </div>
  );
}
