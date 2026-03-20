import { useEffect, useRef, useState } from "react";
import { fetchLeads } from "../../api/leads";
import { exportLeadsCsv, exportLeadsWebhook } from "../../api/leads";
import type { LeadFiltersExport } from "../../types/lead";

// ── Field definitions ─────────────────────────────────────────────────────────

interface FieldDef {
  key: string;
  label: string;
}

const FIELD_GROUPS: { title: string; fields: FieldDef[] }[] = [
  {
    title: "Basic Info",
    fields: [
      { key: "name", label: "Full Name" },
      { key: "email", label: "Email" },
      { key: "phone", label: "Phone" },
      { key: "company", label: "Company" },
      { key: "title", label: "Title" },
    ],
  },
  {
    title: "Lead Data",
    fields: [
      { key: "source", label: "Source" },
      { key: "status", label: "Status" },
      { key: "score", label: "Lead Score" },
      { key: "created_at", label: "Created Date" },
    ],
  },
  {
    title: "Enrichment",
    fields: [
      { key: "linkedin_url", label: "LinkedIn URL" },
      { key: "industry", label: "Industry" },
      { key: "employee_count", label: "Employees" },
      { key: "location", label: "Location" },
      { key: "enrichment_status", label: "Enrichment Status" },
      { key: "enriched_at", label: "Enriched Date" },
    ],
  },
  {
    title: "AI Analysis",
    fields: [
      { key: "ai_qualification", label: "AI Qualification" },
      { key: "ai_icebreakers", label: "AI Icebreakers" },
      { key: "ai_email_angle", label: "AI Email Angle" },
    ],
  },
];

const DEFAULT_FIELDS = new Set([
  "name", "email", "company", "title", "source", "score", "status", "created_at",
]);

// ── Props ─────────────────────────────────────────────────────────────────────

interface ExportModalProps {
  filters: LeadFiltersExport;
  onClose: () => void;
}

// ── Filter pill helpers ───────────────────────────────────────────────────────

function ActiveFilterPills({ filters }: { filters: LeadFiltersExport }) {
  const pills: { label: string; value: string }[] = [];
  if (filters.source) pills.push({ label: "Source", value: filters.source });
  if (filters.status) pills.push({ label: "Status", value: filters.status });
  if (filters.score_min !== undefined || filters.score_max !== undefined) {
    const min = filters.score_min ?? 0;
    const max = filters.score_max ?? 100;
    pills.push({ label: "Score", value: `${min}–${max}` });
  }
  if (filters.search) pills.push({ label: "Search", value: filters.search });
  if (filters.date_from) pills.push({ label: "From", value: filters.date_from });
  if (filters.date_to) pills.push({ label: "To", value: filters.date_to });
  return (
    <div className="flex flex-wrap gap-1.5">
      {pills.map((p) => (
        <span
          key={p.label}
          className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700"
        >
          <span className="text-indigo-400">{p.label}:</span> {p.value}
        </span>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ExportModal({ filters, onClose }: ExportModalProps) {
  const [tab, setTab] = useState<"csv" | "webhook">("csv");
  const [leadCount, setLeadCount] = useState<number | null>(null);
  const hasFilters = Object.values(filters).some((v) => v !== undefined && v !== "");

  // CSV state
  const [selectedFields, setSelectedFields] = useState<Set<string>>(new Set(DEFAULT_FIELDS));
  const [csvLoading, setCsvLoading] = useState(false);
  const [csvResult, setCsvResult] = useState<string | null>(null);
  const [csvError, setCsvError] = useState<string | null>(null);

  // Webhook state
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhookUrlError, setWebhookUrlError] = useState("");
  const [batchSize, setBatchSize] = useState(50);
  const [includeEnrichment, setIncludeEnrichment] = useState(true);
  const [includeAi, setIncludeAi] = useState(false);
  const [webhookLoading, setWebhookLoading] = useState(false);
  const [webhookResult, setWebhookResult] = useState<string | null>(null);
  const [webhookError, setWebhookError] = useState<string | null>(null);

  const overlayRef = useRef<HTMLDivElement>(null);

  // Fetch lead count on open
  useEffect(() => {
    const params: Record<string, string> = { limit: "1", offset: "0" };
    if (filters.source) params.source = filters.source;
    if (filters.status) params.status = filters.status;
    if (filters.score_min !== undefined) params.score_min = String(filters.score_min);
    if (filters.score_max !== undefined) params.score_max = String(filters.score_max);
    if (filters.search) params.search = filters.search;
    if (filters.date_from) params.created_after = filters.date_from;
    if (filters.date_to) params.created_before = filters.date_to;

    fetchLeads(params).then((res) => setLeadCount(res.total)).catch(() => setLeadCount(null));
  }, [filters]);

  // Close on overlay click
  function handleOverlayClick(e: React.MouseEvent) {
    if (e.target === overlayRef.current) onClose();
  }

  // ── Field selection helpers ───────────────────────────────────────────────

  function toggleField(key: string) {
    setSelectedFields((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  function selectAllInGroup(fields: FieldDef[]) {
    setSelectedFields((prev) => {
      const next = new Set(prev);
      fields.forEach((f) => next.add(f.key));
      return next;
    });
  }

  function deselectAllInGroup(fields: FieldDef[]) {
    setSelectedFields((prev) => {
      const next = new Set(prev);
      fields.forEach((f) => next.delete(f.key));
      return next;
    });
  }

  // ── CSV export ────────────────────────────────────────────────────────────

  async function handleCsvExport() {
    if (selectedFields.size === 0) return;
    setCsvLoading(true);
    setCsvError(null);
    setCsvResult(null);
    try {
      // Preserve column order from FIELD_GROUPS
      const orderedFields = FIELD_GROUPS.flatMap((g) =>
        g.fields.filter((f) => selectedFields.has(f.key)).map((f) => f.key),
      );
      const count = await exportLeadsCsv(filters, orderedFields);
      setCsvResult(`Downloaded ${count} lead${count !== 1 ? "s" : ""}`);
    } catch (e: unknown) {
      setCsvError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setCsvLoading(false);
    }
  }

  // ── Webhook export ────────────────────────────────────────────────────────

  function validateWebhookUrl(url: string): string {
    if (!url) return "Webhook URL is required";
    if (!url.startsWith("https://")) return "URL must start with https://";
    try {
      new URL(url);
    } catch {
      return "Invalid URL format";
    }
    return "";
  }

  async function handleWebhookExport() {
    const err = validateWebhookUrl(webhookUrl);
    setWebhookUrlError(err);
    if (err) return;

    setWebhookLoading(true);
    setWebhookError(null);
    setWebhookResult(null);
    try {
      const res = await exportLeadsWebhook({
        webhook_url: webhookUrl,
        filters,
        batch_size: batchSize,
        include_enrichment: includeEnrichment,
        include_ai_analysis: includeAi,
      });
      const domain = res.webhook_url.replace("https://", "");
      setWebhookResult(
        `✓ Dispatched ${res.total_leads} lead${res.total_leads !== 1 ? "s" : ""} in ${res.total_batches} batch${res.total_batches !== 1 ? "es" : ""} to ${domain}`,
      );
    } catch (e: unknown) {
      setWebhookError(e instanceof Error ? e.message : "Webhook export failed");
    } finally {
      setWebhookLoading(false);
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div className="w-full max-w-2xl rounded-xl bg-white shadow-xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Export Leads</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              {leadCount === null
                ? "Counting leads…"
                : hasFilters
                  ? `${leadCount.toLocaleString()} leads match current filters`
                  : `Exporting all leads (${leadCount.toLocaleString()} total)`}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Active filters */}
        {hasFilters && (
          <div className="border-b border-gray-100 px-6 py-3">
            <p className="text-xs font-medium text-gray-500 mb-2">Active filters:</p>
            <ActiveFilterPills filters={filters} />
          </div>
        )}

        {/* Tabs */}
        <div className="flex border-b border-gray-200 px-6">
          {(["csv", "webhook"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`mr-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                tab === t
                  ? "border-indigo-500 text-indigo-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t === "csv" ? "CSV Export" : "Webhook Export"}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {tab === "csv" ? (
            <div className="space-y-5">
              <p className="text-sm text-gray-600">
                Select the columns to include in your CSV file.
              </p>

              {FIELD_GROUPS.map((group) => {
                const allChecked = group.fields.every((f) => selectedFields.has(f.key));
                return (
                  <div key={group.title}>
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                        {group.title}
                      </h3>
                      <div className="flex gap-2">
                        <button
                          onClick={() => selectAllInGroup(group.fields)}
                          className="text-xs text-indigo-600 hover:underline"
                        >
                          Select all
                        </button>
                        <span className="text-gray-300">·</span>
                        <button
                          onClick={() => deselectAllInGroup(group.fields)}
                          className="text-xs text-gray-400 hover:underline"
                        >
                          Deselect all
                        </button>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-1.5">
                      {group.fields.map((f) => (
                        <label
                          key={f.key}
                          className="flex items-center gap-2 rounded-md px-2 py-1.5 cursor-pointer hover:bg-gray-50"
                        >
                          <input
                            type="checkbox"
                            checked={selectedFields.has(f.key)}
                            onChange={() => toggleField(f.key)}
                            className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                          />
                          <span className="text-sm text-gray-700">{f.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="space-y-5">
              {/* Webhook URL */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Webhook URL <span className="text-red-500">*</span>
                </label>
                <input
                  type="url"
                  value={webhookUrl}
                  onChange={(e) => {
                    setWebhookUrl(e.target.value);
                    if (webhookUrlError) setWebhookUrlError(validateWebhookUrl(e.target.value));
                  }}
                  placeholder="https://hooks.example.com/leads"
                  className={`w-full rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 ${
                    webhookUrlError
                      ? "border-red-300 focus:border-red-500 focus:ring-red-500"
                      : "border-gray-300 focus:border-indigo-500 focus:ring-indigo-500"
                  }`}
                />
                {webhookUrlError && (
                  <p className="mt-1 text-xs text-red-600">{webhookUrlError}</p>
                )}
                <p className="mt-1 text-xs text-gray-500">Must be a valid https:// URL</p>
              </div>

              {/* Batch size */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Batch size
                </label>
                <input
                  type="number"
                  value={batchSize}
                  min={1}
                  max={200}
                  onChange={(e) => setBatchSize(Math.max(1, Math.min(200, Number(e.target.value))))}
                  className="w-32 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <p className="mt-1 text-xs text-gray-500">Leads per batch (1–200, default 50)</p>
              </div>

              {/* Toggles */}
              <div className="space-y-3">
                <label className="flex items-center gap-3 cursor-pointer">
                  <button
                    role="switch"
                    aria-checked={includeEnrichment}
                    onClick={() => setIncludeEnrichment((v) => !v)}
                    className={`relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent transition-colors focus:outline-none ${
                      includeEnrichment ? "bg-indigo-600" : "bg-gray-200"
                    }`}
                  >
                    <span
                      className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
                        includeEnrichment ? "translate-x-5" : "translate-x-0"
                      }`}
                    />
                  </button>
                  <span className="text-sm text-gray-700">Include enrichment data</span>
                </label>

                <label className="flex items-center gap-3 cursor-pointer">
                  <button
                    role="switch"
                    aria-checked={includeAi}
                    onClick={() => setIncludeAi((v) => !v)}
                    className={`relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent transition-colors focus:outline-none ${
                      includeAi ? "bg-indigo-600" : "bg-gray-200"
                    }`}
                  >
                    <span
                      className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
                        includeAi ? "translate-x-5" : "translate-x-0"
                      }`}
                    />
                  </button>
                  <span className="text-sm text-gray-700">Include AI analysis</span>
                </label>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex-1 text-sm">
            {tab === "csv" ? (
              <>
                {csvResult && <span className="text-green-700 font-medium">{csvResult}</span>}
                {csvError && <span className="text-red-600">{csvError}</span>}
              </>
            ) : (
              <>
                {webhookResult && <span className="text-green-700 font-medium">{webhookResult}</span>}
                {webhookError && <span className="text-red-600">{webhookError}</span>}
              </>
            )}
          </div>

          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Close
            </button>

            {tab === "csv" ? (
              <button
                onClick={handleCsvExport}
                disabled={csvLoading || selectedFields.size === 0}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed min-w-[140px]"
              >
                {csvLoading ? "Preparing export…" : "Export CSV"}
              </button>
            ) : (
              <button
                onClick={handleWebhookExport}
                disabled={webhookLoading}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed min-w-[140px]"
              >
                {webhookLoading ? "Dispatching…" : "Send to Webhook"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
