import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
  type RowSelectionState,
  type SortingState,
} from "@tanstack/react-table";
import type { Lead } from "../../types/lead";
import ScoreBadge from "./ScoreBadge";

const col = createColumnHelper<Lead>();

function SortIcon({ active, direction }: { active: boolean; direction: string }) {
  if (!active) return <span className="ml-1 text-gray-300">&uarr;&darr;</span>;
  return <span className="ml-1">{direction === "asc" ? "\u2191" : "\u2193"}</span>;
}

interface LeadsTableProps {
  data: Lead[];
  total: number;
  limit: number;
  offset: number;
  sortBy: string;
  sortOrder: "asc" | "desc";
  onSort: (columnId: string) => void;
  onPageChange: (offset: number) => void;
  onPageSizeChange: (size: number) => void;
  rowSelection: RowSelectionState;
  onRowSelectionChange: (sel: RowSelectionState) => void;
  onLeadClick: (leadId: number) => void;
  loading: boolean;
}

export default function LeadsTable({
  data,
  total,
  limit,
  offset,
  sortBy,
  sortOrder,
  onSort,
  onPageChange,
  onPageSizeChange,
  rowSelection,
  onRowSelectionChange,
  onLeadClick,
  loading,
}: LeadsTableProps) {
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
          onClick={() => onLeadClick(info.row.original.id)}
          className="font-medium text-indigo-600 hover:text-indigo-800"
        >
          {info.getValue()}
        </button>
      ),
    }),
    col.accessor("email", { header: "Email" }),
    col.accessor("company", { header: "Company", cell: (info) => info.getValue() || "—" }),
    col.accessor("title", { header: "Title", cell: (info) => info.getValue() || "—" }),
    col.accessor("source", { header: "Source", cell: (info) => info.getValue() || "—" }),
    col.accessor("score", {
      header: "Score",
      cell: (info) => <ScoreBadge score={info.getValue()} />,
    }),
    col.accessor("enrichment_status", { header: "Enrichment" }),
    col.accessor("created_at", {
      header: "Created",
      cell: (info) => new Date(info.getValue()).toLocaleDateString(),
    }),
  ];

  const sorting: SortingState = [{ id: sortBy, desc: sortOrder === "desc" }];

  const table = useReactTable({
    data,
    columns,
    state: { sorting, rowSelection },
    onRowSelectionChange: (updater) => {
      const next = typeof updater === "function" ? updater(rowSelection) : updater;
      onRowSelectionChange(next);
    },
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    pageCount: Math.ceil(total / limit),
    getRowId: (row) => String(row.id),
  });

  const pageIndex = Math.floor(offset / limit);
  const pageCount = Math.ceil(total / limit);
  const showFrom = total === 0 ? 0 : offset + 1;
  const showTo = Math.min(offset + limit, total);

  return (
    <div>
      <div className="overflow-x-auto rounded-md border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => {
                  const canSort = header.column.getCanSort() && header.id !== "select";
                  return (
                    <th
                      key={header.id}
                      onClick={canSort ? () => onSort(header.id) : undefined}
                      className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 ${canSort ? "cursor-pointer select-none hover:text-gray-700" : ""}`}
                      style={header.column.getSize() ? { width: header.column.getSize() } : undefined}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {canSort && <SortIcon active={sortBy === header.id} direction={sortOrder} />}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white">
            {loading ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-sm text-gray-500">
                  Loading...
                </td>
              </tr>
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-sm text-gray-500">
                  No leads found
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

      <div className="mt-3 flex items-center justify-between text-sm text-gray-600">
        <span>
          Showing {showFrom}–{showTo} of {total}
        </span>
        <div className="flex items-center gap-3">
          <select
            value={limit}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="rounded-md border border-gray-300 px-2 py-1 text-sm"
          >
            {[25, 50, 100].map((s) => (
              <option key={s} value={s}>
                {s} / page
              </option>
            ))}
          </select>
          <button
            onClick={() => onPageChange(Math.max(0, offset - limit))}
            disabled={pageIndex === 0}
            className="rounded-md border border-gray-300 px-3 py-1 disabled:opacity-40"
          >
            Prev
          </button>
          <span>
            Page {pageIndex + 1} of {Math.max(1, pageCount)}
          </span>
          <button
            onClick={() => onPageChange(offset + limit)}
            disabled={pageIndex >= pageCount - 1}
            className="rounded-md border border-gray-300 px-3 py-1 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
