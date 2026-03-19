import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
  type RowSelectionState,
} from "@tanstack/react-table";
import { bulkEnrichCompanies, enrichCompany, getCompanies } from "../api/companies";
import type { Company } from "../types/company";
import CompanyDetailPanel from "../components/companies/CompanyDetailPanel";
import AddCompanyModal from "../components/companies/AddCompanyModal";
import CsvUploadModal from "../components/companies/CsvUploadModal";

const col = createColumnHelper<Company>();

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

export default function Companies() {
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

  // Client-side filter
  const [search, setSearch] = useState("");

  // UI state
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showCsvModal, setShowCsvModal] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [bulkEnriching, setBulkEnriching] = useState(false);
  const [enrichingSelected, setEnrichingSelected] = useState(false);

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
      });
      setCompanies(res.items);
      setTotal(res.total);
    } catch {
      showToast("Failed to load companies");
    } finally {
      setLoading(false);
    }
  }, [skip, limit, enrichmentFilter, abmFilter]);

  useEffect(() => {
    fetchCompanies();
  }, [fetchCompanies]);

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
  const columns = [
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
      cell: (info) => info.getValue() || "—",
    }),
    col.accessor("industry", {
      header: "Industry",
      cell: (info) => info.getValue() || "—",
    }),
    col.accessor("employee_count", {
      header: "Employees",
      cell: (info) => {
        const v = info.getValue();
        return v != null ? v.toLocaleString() : "—";
      },
    }),
    col.accessor("enrichment_status", {
      header: "Enrichment",
      cell: (info) => <EnrichmentBadge status={info.getValue()} />,
    }),
    col.accessor("abm_status", {
      header: "ABM",
      cell: (info) => <AbmBadge status={info.getValue()} />,
    }),
    col.accessor("lead_count", {
      header: "Leads",
      cell: (info) => info.getValue(),
    }),
    col.accessor("created_at", {
      header: "Created",
      cell: (info) => relativeDate(info.getValue()),
    }),
  ];

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
          {selectedIds.length > 0 && (
            <button
              onClick={handleEnrichSelected}
              disabled={enrichingSelected}
              className="rounded-md bg-yellow-500 px-3 py-2 text-sm font-medium text-white hover:bg-yellow-600 disabled:opacity-50"
            >
              {enrichingSelected ? "Queuing…" : `Enrich Selected (${selectedIds.length})`}
            </button>
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
                <tr key={hg.id}>
                  {hg.headers.map((header) => (
                    <th
                      key={header.id}
                      className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500"
                      style={header.column.getSize() ? { width: header.column.getSize() } : undefined}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
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
