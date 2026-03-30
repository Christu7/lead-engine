import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
  type RowSelectionState,
} from "@tanstack/react-table";
import { bulkEnrichCompanies, enrichCompany, getCompanies, pullContacts } from "../api/companies";
import type { Company } from "../types/company";
import CompanyDetailPanel from "../components/companies/CompanyDetailPanel";
import AddCompanyModal from "../components/companies/AddCompanyModal";
import CsvUploadModal from "../components/companies/CsvUploadModal";
import { getCustomFieldDefinitions } from "../api/custom_fields";
import type { CustomFieldDefinition } from "../types/custom_field";
import AddCustomFieldModal from "../components/AddCustomFieldModal";
import { useAuth } from "../contexts/AuthContext";

function renderCustomFieldCell(fieldType: string, value: unknown): React.ReactNode {
  if (value == null) return <span className="text-gray-400">—</span>;
  switch (fieldType) {
    case "text": {
      const s = String(value);
      return s.length > 50
        ? <span title={s}>{s.slice(0, 50)}…</span>
        : <span>{s}</span>;
    }
    case "number":
      return <span className="tabular-nums">{Number(value).toLocaleString()}</span>;
    case "date":
      try { return <span>{new Date(String(value)).toLocaleDateString()}</span>; }
      catch { return <span>{String(value)}</span>; }
    case "boolean":
      return value
        ? <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">Yes</span>
        : <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">No</span>;
    case "select":
      return <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">{String(value)}</span>;
    default:
      return <span>{String(value)}</span>;
  }
}

const col = createColumnHelper<Company>();

// ── Sort icon (same pattern as LeadsTable) ───────────────────────────────────

function SortIcon({ active, direction }: { active: boolean; direction: string }) {
  if (!active) return <span className="ml-1 text-gray-300">&uarr;&darr;</span>;
  return <span className="ml-1">{direction === "asc" ? "\u2191" : "\u2193"}</span>;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function relativeDate(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function EnrichmentBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    enriched: "bg-green-100 text-green-800",
    enriching: "bg-yellow-100 text-yellow-800",
    pending: "bg-gray-100 text-gray-600",
    partial: "bg-orange-100 text-orange-800",
    failed: "bg-red-100 text-red-800",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[status] ?? styles.pending}`}
    >
      {status === "enriching" && (
        <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
      )}
      {status}
    </span>
  );
}

function AbmBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    target: "bg-blue-100 text-blue-800",
    active: "bg-green-100 text-green-800",
    inactive: "bg-gray-100 text-gray-600",
  };
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[status] ?? styles.target}`}>
      {status}
    </span>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────

const SORT_DEFAULTS = { sort_by: "created_at", sort_order: "desc" } as const;

export default function Companies() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin" || user?.role === "superadmin";

  // Server-side data
  const [companies, setCompanies] = useState<Company[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  // Pagination
  const [limit, setLimit] = useState(25);
  const [skip, setSkip] = useState(0);

  // Server-side filters
  const [enrichmentFilter, setEnrichmentFilter] = useState("");
  const [abmFilter, setAbmFilter] = useState("");

  // Sort state (URL-backed)
  const sortBy = searchParams.get("sort_by") || SORT_DEFAULTS.sort_by;
  const sortOrder = (searchParams.get("sort_order") || SORT_DEFAULTS.sort_order) as "asc" | "desc";

  const handleSort = useCallback(
    (columnId: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        const currentSort = prev.get("sort_by") || SORT_DEFAULTS.sort_by;
        const currentOrder = prev.get("sort_order") || SORT_DEFAULTS.sort_order;
        if (currentSort === columnId) {
          next.set("sort_order", currentOrder === "asc" ? "desc" : "asc");
        } else {
          next.set("sort_by", columnId);
          next.set("sort_order", "asc");
        }
        return next;
      });
      setSkip(0);
    },
    [setSearchParams],
  );

  // Client-side filter
  const [search, setSearch] = useState("");

  // UI state
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showCsvModal, setShowCsvModal] = useState(false);
  const [showAddFieldModal, setShowAddFieldModal] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [bulkEnriching, setBulkEnriching] = useState(false);
  const [enrichingSelected, setEnrichingSelected] = useState(false);

  // Custom field definitions
  const [customFieldDefs, setCustomFieldDefs] = useState<CustomFieldDefinition[]>([]);

  useEffect(() => {
    getCustomFieldDefinitions("company").then(setCustomFieldDefs).catch(() => {});
  }, []); // fetch once on mount

  // Pull Contacts state
  const [showPullPopover, setShowPullPopover] = useState(false);
  const [pullSeniorities, setPullSeniorities] = useState<string[]>(["vp", "director", "c_suite"]);
  const [pullTitles, setPullTitles] = useState("");
  const [pullLimit, setPullLimit] = useState(25);
  const [pullingContacts, setPullingContacts] = useState(false);
  const [pullProgress, setPullProgress] = useState("");

  const tablePollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopTablePolling = () => {
    if (tablePollRef.current !== null) {
      clearInterval(tablePollRef.current);
      tablePollRef.current = null;
    }
  };

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const fetchCompanies = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getCompanies({
        skip,
        limit,
        enrichment_status: enrichmentFilter || undefined,
        abm_status: abmFilter || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
      });
      setCompanies(res.items);
      setTotal(res.total);
    } catch {
      showToast("Failed to load companies");
    } finally {
      setLoading(false);
    }
  }, [skip, limit, enrichmentFilter, abmFilter, sortBy, sortOrder]);

  useEffect(() => {
    fetchCompanies();
  }, [fetchCompanies]);

  // Poll every 5 s while any visible company is still enriching
  useEffect(() => {
    const anyEnriching = companies.some((c) => c.enrichment_status === "enriching");
    if (anyEnriching) {
      if (tablePollRef.current === null) {
        tablePollRef.current = setInterval(fetchCompanies, 5000);
      }
    } else {
      stopTablePolling();
    }
    return stopTablePolling;
  }, [companies, fetchCompanies]);

  // Ensure interval is cleared on unmount regardless of companies state
  useEffect(() => stopTablePolling, []);

  // Reset to page 0 when filters change
  useEffect(() => {
    setSkip(0);
  }, [enrichmentFilter, abmFilter, limit]);

  // Client-side search filter
  const filtered = useMemo(() => {
    if (!search.trim()) return companies;
    const q = search.toLowerCase();
    return companies.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        (c.domain ?? "").toLowerCase().includes(q),
    );
  }, [companies, search]);

  // ── Table columns ──
  const columns = useMemo(() => [
    col.display({
      id: "select",
      header: ({ table }) => (
        <input
          type="checkbox"
          checked={table.getIsAllRowsSelected()}
          onChange={table.getToggleAllRowsSelectedHandler()}
          className="rounded border-gray-300"
        />
      ),
      cell: ({ row }) => (
        <input
          type="checkbox"
          checked={row.getIsSelected()}
          onChange={row.getToggleSelectedHandler()}
          className="rounded border-gray-300"
        />
      ),
      size: 40,
    }),
    col.accessor("name", {
      header: "Name",
      enableSorting: true,
      cell: (info) => (
        <button
          onClick={() => setSelectedCompanyId(info.row.original.id)}
          className="font-medium text-indigo-600 hover:text-indigo-800"
        >
          {info.getValue()}
        </button>
      ),
    }),
    col.accessor("domain", {
      header: "Domain",
      enableSorting: true,
      cell: (info) => info.getValue() || "—",
    }),
    col.accessor("industry", {
      header: "Industry",
      enableSorting: true,
      cell: (info) => info.getValue() || "—",
    }),
    col.accessor("employee_count", {
      header: "Employees",
      enableSorting: true,
      cell: (info) => {
        const v = info.getValue();
        return v != null ? v.toLocaleString() : "—";
      },
    }),
    col.accessor("enrichment_status", {
      header: "Enrichment",
      enableSorting: true,
      cell: (info) => <EnrichmentBadge status={info.getValue()} />,
    }),
    col.accessor("abm_status", {
      header: "ABM",
      enableSorting: true,
      cell: (info) => <AbmBadge status={info.getValue()} />,
    }),
    col.accessor("lead_count", {
      header: "Leads",
      enableSorting: true,
      cell: (info) => info.getValue(),
    }),
    col.accessor("created_at", {
      header: "Created",
      enableSorting: true,
      cell: (info) => relativeDate(info.getValue()),
    }),
    ...(customFieldDefs).filter(fd => fd.show_in_table).map(fd =>
      col.display({
        id: `custom_${fd.field_key}`,
        header: fd.field_label,
        cell: ({ row }) => {
          const val = (row.original.custom_fields ?? {})[fd.field_key];
          return renderCustomFieldCell(fd.field_type, val);
        },
      })
    ),
  ], [customFieldDefs, sortBy, sortOrder]);

  const table = useReactTable({
    data: filtered,
    columns,
    state: { rowSelection },
    onRowSelectionChange: (updater) => {
      const next = typeof updater === "function" ? updater(rowSelection) : updater;
      setRowSelection(next);
    },
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    pageCount: Math.ceil(total / limit),
    getRowId: (row) => row.id,
  });

  const selectedIds = Object.keys(rowSelection);
  const pageIndex = Math.floor(skip / limit);
  const pageCount = Math.ceil(total / limit);
  const showFrom = total === 0 ? 0 : skip + 1;
  const showTo = Math.min(skip + limit, total);

  // ── Bulk actions ──
  const handleBulkEnrich = async () => {
    setBulkEnriching(true);
    try {
      const res = await bulkEnrichCompanies();
      showToast(`Queued ${res.queued} companies for enrichment`);
      fetchCompanies();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Bulk enrich failed");
    } finally {
      setBulkEnriching(false);
    }
  };

  const handleEnrichSelected = async () => {
    setEnrichingSelected(true);
    let ok = 0;
    for (const id of selectedIds) {
      try {
        await enrichCompany(id);
        ok++;
      } catch {
        // individual failure — continue others
      }
    }
    showToast(`Queued ${ok} of ${selectedIds.length} for enrichment`);
    setRowSelection({});
    setEnrichingSelected(false);
    fetchCompanies();
  };

  // Derive enriched/unenriched split from current selection
  const selectedCompanies = useMemo(
    () => selectedIds.map((id) => companies.find((c) => c.id === id)).filter(Boolean) as typeof companies,
    [selectedIds, companies],
  );
  const enrichedSelectedIds = selectedCompanies
    .filter((c) => c.enrichment_status === "enriched")
    .map((c) => c.id);
  const unenrichedCount = selectedCompanies.length - enrichedSelectedIds.length;

  const handlePullContacts = async () => {
    setShowPullPopover(false);
    setPullingContacts(true);
    const titles = pullTitles
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    let ok = 0;
    for (let i = 0; i < enrichedSelectedIds.length; i++) {
      setPullProgress(`Pulling contacts from company ${i + 1} of ${enrichedSelectedIds.length}…`);
      try {
        await pullContacts(enrichedSelectedIds[i], { titles, seniorities: pullSeniorities, limit: pullLimit });
        ok++;
      } catch {
        // individual failure — continue others
      }
    }
    setPullingContacts(false);
    setPullProgress("");
    setRowSelection({});
    showToast(`Pulled contacts from ${ok} of ${enrichedSelectedIds.length} companies`);
    fetchCompanies();
  };

  const SENIORITY_OPTIONS = [
    { value: "owner", label: "Owner" },
    { value: "founder", label: "Founder" },
    { value: "c_suite", label: "C-Suite" },
    { value: "vp", label: "VP" },
    { value: "director", label: "Director" },
    { value: "manager", label: "Manager" },
    { value: "senior", label: "Senior" },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Companies</h1>

      {/* ── Toolbar ── */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <input
          type="text"
          placeholder="Search by name or domain…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />

        {/* Enrichment Status filter */}
        <select
          value={enrichmentFilter}
          onChange={(e) => setEnrichmentFilter(e.target.value)}
          className="rounded-md border border-gray-300 px-2.5 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          <option value="">All Enrichment</option>
          <option value="pending">Pending</option>
          <option value="enriching">Enriching</option>
          <option value="enriched">Enriched</option>
          <option value="partial">Partial</option>
          <option value="failed">Failed</option>
        </select>

        {/* ABM Status filter */}
        <select
          value={abmFilter}
          onChange={(e) => setAbmFilter(e.target.value)}
          className="rounded-md border border-gray-300 px-2.5 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          <option value="">All ABM</option>
          <option value="target">Target</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>

        <div className="ml-auto flex items-center gap-2">
          {/* Pull progress text */}
          {pullingContacts && (
            <span className="text-xs text-gray-500">{pullProgress}</span>
          )}

          {selectedIds.length > 0 && (
            <button
              onClick={handleEnrichSelected}
              disabled={enrichingSelected || pullingContacts}
              className="rounded-md bg-yellow-500 px-3 py-2 text-sm font-medium text-white hover:bg-yellow-600 disabled:opacity-50"
            >
              {enrichingSelected ? "Queuing…" : `Enrich Selected (${selectedIds.length})`}
            </button>
          )}

          {/* Pull Contacts button + popover */}
          {selectedIds.length > 0 && (
            <div className="relative">
              <button
                onClick={() => setShowPullPopover((v) => !v)}
                disabled={pullingContacts || enrichingSelected}
                className="rounded-md bg-indigo-500 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-600 disabled:opacity-50"
              >
                {pullingContacts ? pullProgress || "Pulling…" : `Pull Contacts (${selectedIds.length})`}
              </button>

              {showPullPopover && (
                <div className="absolute right-0 top-full z-50 mt-1 w-72 rounded-lg border border-gray-200 bg-white p-4 shadow-lg">
                  <p className="mb-3 text-sm font-semibold text-gray-900">Pull Contacts Options</p>

                  {/* Seniority */}
                  <div className="mb-3">
                    <p className="mb-1.5 text-xs font-medium text-gray-700">Seniority</p>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                      {SENIORITY_OPTIONS.map((opt) => (
                        <label key={opt.value} className="flex items-center gap-1.5 text-xs text-gray-700">
                          <input
                            type="checkbox"
                            checked={pullSeniorities.includes(opt.value)}
                            onChange={(e) =>
                              setPullSeniorities((prev) =>
                                e.target.checked
                                  ? [...prev, opt.value]
                                  : prev.filter((s) => s !== opt.value),
                              )
                            }
                            className="rounded border-gray-300"
                          />
                          {opt.label}
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Titles */}
                  <div className="mb-3">
                    <label className="mb-1 block text-xs font-medium text-gray-700">
                      Titles (optional, comma-separated)
                    </label>
                    <input
                      type="text"
                      value={pullTitles}
                      onChange={(e) => setPullTitles(e.target.value)}
                      placeholder="CEO, Head of IT, Digital Transformation"
                      className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-xs focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>

                  {/* Limit */}
                  <div className="mb-3">
                    <label className="mb-1 block text-xs font-medium text-gray-700">
                      Limit per company (max 100)
                    </label>
                    <input
                      type="number"
                      value={pullLimit}
                      min={1}
                      max={100}
                      onChange={(e) => setPullLimit(Math.min(100, Math.max(1, Number(e.target.value))))}
                      className="w-24 rounded-md border border-gray-300 px-2.5 py-1.5 text-xs focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>

                  {/* Warning for unenriched */}
                  {unenrichedCount > 0 && (
                    <p className="mb-3 rounded-md bg-yellow-50 px-2.5 py-1.5 text-xs text-yellow-700">
                      ⚠ {unenrichedCount} {unenrichedCount === 1 ? "company" : "companies"} will be skipped (not yet enriched)
                    </p>
                  )}

                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setShowPullPopover(false)}
                      className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handlePullContacts}
                      disabled={enrichedSelectedIds.length === 0}
                      className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      Pull from {enrichedSelectedIds.length} {enrichedSelectedIds.length === 1 ? "company" : "companies"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          <button
            onClick={handleBulkEnrich}
            disabled={bulkEnriching}
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {bulkEnriching ? "Queuing…" : "Bulk Enrich"}
          </button>
          <button
            onClick={() => setShowCsvModal(true)}
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Upload CSV
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Add Company
          </button>
        </div>
      </div>

      {/* ── Table ── */}
      <div>
        <div className="overflow-x-auto rounded-md border border-gray-200">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id} className="group">
                  {hg.headers.map((header) => {
                    const sortable = header.column.columnDef.enableSorting === true;
                    const isActive = sortable && sortBy === header.column.id;
                    return (
                      <th
                        key={header.id}
                        onClick={sortable ? () => handleSort(header.column.id) : undefined}
                        className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 select-none${sortable ? " cursor-pointer hover:text-gray-700" : ""}`}
                        style={header.column.getSize() ? { width: header.column.getSize() } : undefined}
                      >
                        <span className="inline-flex items-center gap-0.5">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {sortable && (
                            <SortIcon active={isActive} direction={sortOrder} />
                          )}
                        </span>
                      </th>
                    );
                  })}
                  {isAdmin && (
                    <th className="py-3 pr-3 text-left">
                      <button
                        onClick={() => setShowAddFieldModal(true)}
                        title="Add custom column"
                        className="opacity-0 group-hover:opacity-100 transition-opacity rounded px-1.5 py-0.5 text-xs font-medium text-gray-400 hover:bg-gray-200 hover:text-gray-600"
                      >
                        +
                      </button>
                    </th>
                  )}
                </tr>
              ))}
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {loading ? (
                <tr>
                  <td colSpan={columns.length} className="px-4 py-8 text-center text-sm text-gray-500">
                    Loading…
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={columns.length} className="px-4 py-8 text-center text-sm text-gray-500">
                    No companies found
                  </td>
                </tr>
              ) : (
                table.getRowModel().rows.map((row) => (
                  <tr key={row.id} className="hover:bg-gray-50">
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="whitespace-nowrap px-4 py-3 text-sm text-gray-700">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="mt-3 flex items-center justify-between text-sm text-gray-600">
          <span>
            Showing {showFrom}–{showTo} of {total}
          </span>
          <div className="flex items-center gap-3">
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="rounded-md border border-gray-300 px-2 py-1 text-sm"
            >
              {[25, 50, 100].map((s) => (
                <option key={s} value={s}>
                  {s} / page
                </option>
              ))}
            </select>
            <button
              onClick={() => setSkip(Math.max(0, skip - limit))}
              disabled={pageIndex === 0}
              className="rounded-md border border-gray-300 px-3 py-1 disabled:opacity-40"
            >
              Prev
            </button>
            <span>
              Page {pageIndex + 1} of {Math.max(1, pageCount)}
            </span>
            <button
              onClick={() => setSkip(skip + limit)}
              disabled={pageIndex >= pageCount - 1}
              className="rounded-md border border-gray-300 px-3 py-1 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* ── Modals ── */}
      {showAddModal && (
        <AddCompanyModal
          onClose={() => setShowAddModal(false)}
          onCreated={() => {
            fetchCompanies();
            showToast("Company created");
          }}
        />
      )}
      {showCsvModal && (
        <CsvUploadModal
          onClose={() => setShowCsvModal(false)}
          onUploaded={fetchCompanies}
        />
      )}
      {showAddFieldModal && (
        <AddCustomFieldModal
          entityType="company"
          onCreated={(def) => {
            setShowAddFieldModal(false);
            setCustomFieldDefs((prev) => [...prev, def]);
          }}
          onClose={() => setShowAddFieldModal(false)}
        />
      )}

      {/* ── Detail Panel ── */}
      <CompanyDetailPanel
        companyId={selectedCompanyId}
        onClose={() => setSelectedCompanyId(null)}
        onEnriched={fetchCompanies}
      />

      {/* ── Toast ── */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-[60] rounded-md bg-gray-900 px-4 py-3 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}
