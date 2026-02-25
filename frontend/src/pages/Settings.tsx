import { useEffect, useState } from "react";
import {
  fetchRoutingSettings,
  updateRoutingSettings,
  fetchEnrichmentSettings,
  updateEnrichmentSettings,
} from "../api/settings";
import type { RoutingSettings, EnrichmentSettings } from "../types/settings";

export default function Settings() {
  // Routing state
  const [routing, setRouting] = useState<RoutingSettings>({
    ghl_inbound_webhook_url: "",
    ghl_outbound_webhook_url: "",
    score_inbound_threshold: 70,
    score_outbound_threshold: 40,
  });
  const [routingLoading, setRoutingLoading] = useState(true);
  const [routingSaving, setRoutingSaving] = useState(false);
  const [routingMsg, setRoutingMsg] = useState("");

  // Enrichment state
  const [enrichment, setEnrichment] = useState<EnrichmentSettings>({
    apollo_api_key: "",
    clearbit_api_key: "",
    proxycurl_api_key: "",
  });
  const [enrichmentLoading, setEnrichmentLoading] = useState(true);
  const [enrichmentSaving, setEnrichmentSaving] = useState(false);
  const [enrichmentMsg, setEnrichmentMsg] = useState("");

  useEffect(() => {
    fetchRoutingSettings()
      .then((data) => setRouting({
        ghl_inbound_webhook_url: data.ghl_inbound_webhook_url || "",
        ghl_outbound_webhook_url: data.ghl_outbound_webhook_url || "",
        score_inbound_threshold: data.score_inbound_threshold,
        score_outbound_threshold: data.score_outbound_threshold,
      }))
      .catch(() => setRoutingMsg("Failed to load routing settings"))
      .finally(() => setRoutingLoading(false));

    fetchEnrichmentSettings()
      .then((data) => setEnrichment({
        apollo_api_key: data.apollo_api_key || "",
        clearbit_api_key: data.clearbit_api_key || "",
        proxycurl_api_key: data.proxycurl_api_key || "",
      }))
      .catch(() => setEnrichmentMsg("Failed to load enrichment settings"))
      .finally(() => setEnrichmentLoading(false));
  }, []);

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

  const saveEnrichment = async () => {
    setEnrichmentSaving(true);
    setEnrichmentMsg("");
    try {
      await updateEnrichmentSettings({
        apollo_api_key: enrichment.apollo_api_key || null,
        clearbit_api_key: enrichment.clearbit_api_key || null,
        proxycurl_api_key: enrichment.proxycurl_api_key || null,
      });
      setEnrichmentMsg("Enrichment settings saved");
    } catch {
      setEnrichmentMsg("Failed to save enrichment settings");
    } finally {
      setEnrichmentSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900">Settings</h1>

      {/* GHL Routing & Thresholds */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">GHL Routing & Thresholds</h2>
        {routingLoading ? (
          <p className="text-gray-500 text-sm">Loading...</p>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Inbound Webhook URL</label>
              <input
                type="text"
                value={routing.ghl_inbound_webhook_url || ""}
                onChange={(e) => setRouting({ ...routing, ghl_inbound_webhook_url: e.target.value })}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="https://..."
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Outbound Webhook URL</label>
              <input
                type="text"
                value={routing.ghl_outbound_webhook_url || ""}
                onChange={(e) => setRouting({ ...routing, ghl_outbound_webhook_url: e.target.value })}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="https://..."
              />
            </div>
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
              {routingSaving ? "Saving..." : "Save Routing Settings"}
            </button>
          </div>
        )}
      </div>

      {/* Enrichment API Keys */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Enrichment API Keys</h2>
        {enrichmentLoading ? (
          <p className="text-gray-500 text-sm">Loading...</p>
        ) : (
          <div className="space-y-4">
            {(["apollo_api_key", "clearbit_api_key", "proxycurl_api_key"] as const).map((key) => (
              <div key={key}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {key.replace(/_/g, " ").replace(/\bapi\b/i, "API").replace(/\bkey\b/i, "Key")}
                </label>
                <input
                  type="password"
                  value={enrichment[key] || ""}
                  onChange={(e) => setEnrichment({ ...enrichment, [key]: e.target.value })}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="sk-..."
                />
              </div>
            ))}
            {enrichmentMsg && (
              <p className={`text-sm ${enrichmentMsg.includes("Failed") ? "text-red-600" : "text-green-600"}`}>
                {enrichmentMsg}
              </p>
            )}
            <button
              onClick={saveEnrichment}
              disabled={enrichmentSaving}
              className="px-4 py-2 text-sm text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
            >
              {enrichmentSaving ? "Saving..." : "Save Enrichment Settings"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
