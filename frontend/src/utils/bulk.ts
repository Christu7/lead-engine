/**
 * Run an async operation over every item in `items` concurrently via
 * Promise.allSettled.  Returns the items partitioned into succeeded / failed
 * sets so callers can keep failed items selected and show an accurate count.
 */
export interface BulkResult<T> {
  succeeded: T[];
  failed: T[];
}

export async function runBulk<T>(
  items: T[],
  operation: (item: T) => Promise<unknown>,
): Promise<BulkResult<T>> {
  const results = await Promise.allSettled(items.map(operation));
  return {
    succeeded: items.filter((_, i) => results[i].status === "fulfilled"),
    failed: items.filter((_, i) => results[i].status === "rejected"),
  };
}

/**
 * Build a human-readable toast message for a bulk operation result.
 *
 * @param action - past-tense phrase describing what happened, e.g. "deleted"
 *   or "queued for enrichment"
 */
export function bulkResultToast(action: string, succeeded: number, failed: number): string {
  if (failed === 0) return `${succeeded} ${action}`;
  if (succeeded === 0) return `All ${failed} failed`;
  return `${succeeded} ${action}, ${failed} failed`;
}
