import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { RowSelectionState } from "@tanstack/react-table";
import { useLeads } from "../hooks/useLeads";
import LeadsToolbar from "../components/leads/LeadsToolbar";
import LeadsFilters from "../components/leads/LeadsFilters";
import LeadsTable from "../components/leads/LeadsTable";
import LeadSlideOver from "../components/leads/LeadSlideOver";
import ExportModal from "../components/leads/ExportModal";
import DeleteConfirmModal from "../components/DeleteConfirmModal";
import type { LeadFiltersExport } from "../types/lead";
import { getCustomFieldDefinitions } from "../api/custom_fields";
import type { CustomFieldDefinition } from "../types/custom_field";
import { useAuth } from "../contexts/AuthContext";
import { deleteLead } from "../api/leads";
import { runBulk, bulkResultToast } from "../utils/bulk";

export default function Leads() {
  const [searchParams] = useSearchParams();
  const { user, clientVersion } = useAuth();
  const { items, total, loading, limit, offset, sortBy, sortOrder, setFilter, setSort } = useLeads(clientVersion);

  const [showFilters, setShowFilters] = useState(false);
  const [selectedLeadId, setSelectedLeadId] = useState<number | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [showExportModal, setShowExportModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [customFieldDefs, setCustomFieldDefs] = useState<CustomFieldDefinition[]>([]);

  useEffect(() => {
    getCustomFieldDefinitions("lead").then(setCustomFieldDefs).catch(() => {});
  }, [clientVersion]); // re-fetch when workspace changes

  const isAdmin = user?.role === "admin" || user?.role === "superadmin";

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

  const selectedLeadIds = Object.keys(rowSelection).map(Number);

  const handleDeleteSelected = async () => {
    setDeleting(true);
    const { succeeded, failed } = await runBulk(selectedLeadIds, deleteLead);
    setDeleting(false);
    setShowDeleteModal(false);
    setToast(bulkResultToast("deleted", succeeded.length, failed.length));
    setTimeout(() => setToast(null), 4000);
    // Keep failed items selected so the user can retry or investigate
    if (failed.length > 0) {
      setRowSelection(Object.fromEntries(failed.map((id) => [String(id), true])));
    } else {
      setRowSelection({});
    }
    setFilter("offset", "0");
  };

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
            selectedCount={selectedLeadIds.length}
            onDeleteSelected={selectedLeadIds.length > 0 ? () => setShowDeleteModal(true) : undefined}
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
        customFieldDefs={customFieldDefs}
        isAdmin={isAdmin}
        onCustomFieldAdded={(def) => setCustomFieldDefs((prev) => [...prev, def])}
      />

      <LeadSlideOver leadId={selectedLeadId} onClose={() => setSelectedLeadId(null)} />

      {showExportModal && (
        <ExportModal
          filters={exportFilters}
          onClose={() => setShowExportModal(false)}
        />
      )}

      {showDeleteModal && (
        <DeleteConfirmModal
          count={selectedLeadIds.length}
          entityLabel="lead"
          onConfirm={handleDeleteSelected}
          onCancel={() => setShowDeleteModal(false)}
          deleting={deleting}
        />
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-[60] rounded-md bg-gray-900 px-4 py-3 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}
