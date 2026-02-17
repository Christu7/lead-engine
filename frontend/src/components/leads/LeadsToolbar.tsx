import { useEffect, useState } from "react";

interface LeadsToolbarProps {
  search: string;
  onSearchChange: (value: string) => void;
  showFilters: boolean;
  onToggleFilters: () => void;
  selectedCount: number;
}

export default function LeadsToolbar({ search, onSearchChange, showFilters, onToggleFilters, selectedCount }: LeadsToolbarProps) {
  const [localSearch, setLocalSearch] = useState(search);

  useEffect(() => {
    setLocalSearch(search);
  }, [search]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (localSearch !== search) {
        onSearchChange(localSearch);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [localSearch, search, onSearchChange]);

  return (
    <div className="flex items-center gap-3">
      <div className="relative flex-1 max-w-sm">
        <input
          type="text"
          placeholder="Search leads..."
          value={localSearch}
          onChange={(e) => setLocalSearch(e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>
      <button
        onClick={onToggleFilters}
        className={`rounded-md border px-3 py-2 text-sm font-medium ${
          showFilters ? "border-indigo-500 bg-indigo-50 text-indigo-700" : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
        }`}
      >
        Filters
      </button>
      {selectedCount > 0 && (
        <span className="text-sm text-gray-600">{selectedCount} selected</span>
      )}
    </div>
  );
}
