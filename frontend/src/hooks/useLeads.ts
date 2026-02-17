import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { fetchLeads } from "../api/leads";
import type { Lead } from "../types/lead";

const DEFAULTS = {
  limit: "25",
  sort_by: "created_at",
  sort_order: "desc",
  offset: "0",
};

export function useLeads() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState<Lead[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const param = (key: string) => searchParams.get(key) || DEFAULTS[key as keyof typeof DEFAULTS] || "";

  const limit = Number(param("limit")) || 25;
  const offset = Number(param("offset")) || 0;
  const sortBy = param("sort_by");
  const sortOrder = param("sort_order") as "asc" | "desc";

  const setFilter = useCallback(
    (key: string, value: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value) {
          next.set(key, value);
        } else {
          next.delete(key);
        }
        if (key !== "offset") {
          next.set("offset", "0");
        }
        return next;
      });
    },
    [setSearchParams],
  );

  const setSort = useCallback(
    (columnId: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        const currentSort = prev.get("sort_by") || DEFAULTS.sort_by;
        const currentOrder = prev.get("sort_order") || DEFAULTS.sort_order;
        if (currentSort === columnId) {
          next.set("sort_order", currentOrder === "asc" ? "desc" : "asc");
        } else {
          next.set("sort_by", columnId);
          next.set("sort_order", "desc");
        }
        next.set("offset", "0");
        return next;
      });
    },
    [setSearchParams],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    const filters: Record<string, string> = {};
    for (const [key, value] of searchParams.entries()) {
      filters[key] = value;
    }
    if (!filters.limit) filters.limit = DEFAULTS.limit;
    if (!filters.sort_by) filters.sort_by = DEFAULTS.sort_by;
    if (!filters.sort_order) filters.sort_order = DEFAULTS.sort_order;

    fetchLeads(filters as Record<string, string>)
      .then((data) => {
        if (!cancelled) {
          setItems(data.items);
          setTotal(data.total);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [searchParams]);

  return { items, total, loading, limit, offset, sortBy, sortOrder, setFilter, setSort };
}
