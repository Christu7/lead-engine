interface LeadsFiltersProps {
  params: URLSearchParams;
  setFilter: (key: string, value: string) => void;
}

export default function LeadsFilters({ params, setFilter }: LeadsFiltersProps) {
  const val = (key: string) => params.get(key) || "";

  const clearAll = () => {
    for (const key of ["source", "status", "score_min", "score_max", "created_after", "created_before"]) {
      setFilter(key, "");
    }
  };

  return (
    <div className="rounded-md border border-gray-200 bg-gray-50 p-4">
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Source</label>
          <input
            type="text"
            value={val("source")}
            onChange={(e) => setFilter("source", e.target.value)}
            placeholder="e.g. website"
            className="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
          <select
            value={val("status")}
            onChange={(e) => setFilter("status", e.target.value)}
            className="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">All</option>
            <option value="new">New</option>
            <option value="enriched">Enriched</option>
            <option value="scored">Scored</option>
            <option value="routed">Routed</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Score Min</label>
          <input
            type="number"
            min={0}
            max={100}
            value={val("score_min")}
            onChange={(e) => setFilter("score_min", e.target.value)}
            className="w-20 rounded-md border border-gray-300 px-2.5 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Score Max</label>
          <input
            type="number"
            min={0}
            max={100}
            value={val("score_max")}
            onChange={(e) => setFilter("score_max", e.target.value)}
            className="w-20 rounded-md border border-gray-300 px-2.5 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Created After</label>
          <input
            type="date"
            value={val("created_after")}
            onChange={(e) => setFilter("created_after", e.target.value)}
            className="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Created Before</label>
          <input
            type="date"
            value={val("created_before")}
            onChange={(e) => setFilter("created_before", e.target.value)}
            className="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <button
          onClick={clearAll}
          className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Clear
        </button>
      </div>
    </div>
  );
}
