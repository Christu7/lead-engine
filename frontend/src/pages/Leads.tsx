import { useCallback, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { RowSelectionState } from "@tanstack/react-table";
import { useLeads } from "../hooks/useLeads";
import LeadsToolbar from "../components/leads/LeadsToolbar";
import LeadsFilters from "../components/leads/LeadsFilters";
import LeadsTable from "../components/leads/LeadsTable";
import LeadSlideOver from "../components/leads/LeadSlideOver";
import ExportModal from "../components/leads/ExportModal";
import type { LeadFiltersExport } from "../types/lead";

export default function Leads() {
  const [searchParams] = useSearchParams();
  const { items, total, loading, limit, offset, sortBy, sortOrder, setFilter, setSort } = useLeads();

  const [showFilters, setShowFilters] = useState(false);
  const [selectedLeadId, setSelectedLeadId] = useState<number | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [showExportModal, setShowExportModal] = useState(false);

  const search = searchParams.get("search") || "";

  const handleSearchChange = useCallback(
    (value: string) => setFilter("search", value),
    [setFilter],
  );

  const handlePageChange = useCallback(
    (newOffset: number) => setFilter("offset", String(newOffset)),
    [setFilter],
  );

  const handlePageSizeChange = useCallback(
    (size: number) => {
      setFilter("limit", String(size));
    },
    [setFilter],
  );

  // Build export filters from current URL search params
  const exportFilters: LeadFiltersExport = {
    source: searchParams.get("source") || undefined,
    status: searchParams.get("status") || undefined,
    score_min: searchParams.get("score_min") ? Number(searchParams.get("score_min")) : undefined,
    score_max: searchParams.get("score_max") ? Number(searchParams.get("score_max")) : undefined,
    date_from: searchParams.get("created_after") || undefined,
    date_to: searchParams.get("created_before") || undefined,
    search: searchParams.get("search") || undefined,
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Leads</h1>

      <div className="flex items-center justify-between gap-3">
        <div className="flex-1">
          <LeadsToolbar
            search={search}
            onSearchChange={handleSearchChange}
            showFilters={showFilters}
            onToggleFilters={() => setShowFilters((v) => !v)}
            selectedCount={Object.keys(rowSelection).length}
          />
        </div>
        <button
          onClick={() => setShowExportModal(true)}
          className="flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 shadow-sm"
        >
          <svg className="h-4 w-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Export
        </button>
      </div>

      {showFilters && <LeadsFilters params={searchParams} setFilter={setFilter} />}

      <LeadsTable
        data={items}
        total={total}
        limit={limit}
        offset={offset}
        sortBy={sortBy}
        sortOrder={sortOrder}
        onSort={setSort}
        onPageChange={handlePageChange}
        onPageSizeChange={handlePageSizeChange}
        rowSelection={rowSelection}
        onRowSelectionChange={setRowSelection}
        onLeadClick={setSelectedLeadId}
        loading={loading}
      />

      <LeadSlideOver leadId={selectedLeadId} onClose={() => setSelectedLeadId(null)} />

      {showExportModal && (
        <ExportModal
          filters={exportFilters}
          onClose={() => setShowExportModal(false)}
        />
      )}
    </div>
  );
}
