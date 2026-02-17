import { useCallback, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { RowSelectionState } from "@tanstack/react-table";
import { useLeads } from "../hooks/useLeads";
import LeadsToolbar from "../components/leads/LeadsToolbar";
import LeadsFilters from "../components/leads/LeadsFilters";
import LeadsTable from "../components/leads/LeadsTable";
import LeadSlideOver from "../components/leads/LeadSlideOver";

export default function Leads() {
  const [searchParams] = useSearchParams();
  const { items, total, loading, limit, offset, sortBy, sortOrder, setFilter, setSort } = useLeads();

  const [showFilters, setShowFilters] = useState(false);
  const [selectedLeadId, setSelectedLeadId] = useState<number | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

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

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Leads</h1>

      <LeadsToolbar
        search={search}
        onSearchChange={handleSearchChange}
        showFilters={showFilters}
        onToggleFilters={() => setShowFilters((v) => !v)}
        selectedCount={Object.keys(rowSelection).length}
      />

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
    </div>
  );
}
