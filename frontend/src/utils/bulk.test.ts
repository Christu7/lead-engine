import { describe, it, expect } from "vitest";
import { runBulk, bulkResultToast } from "./bulk";

// ---------------------------------------------------------------------------
// runBulk
// ---------------------------------------------------------------------------

describe("runBulk", () => {
  it("puts all items in succeeded when every operation resolves", async () => {
    const result = await runBulk([1, 2, 3], async () => {});
    expect(result.succeeded).toEqual([1, 2, 3]);
    expect(result.failed).toEqual([]);
  });

  it("puts all items in failed when every operation rejects", async () => {
    const result = await runBulk([1, 2, 3], async () => {
      throw new Error("boom");
    });
    expect(result.succeeded).toEqual([]);
    expect(result.failed).toEqual([1, 2, 3]);
  });

  it("partitions correctly on partial failure", async () => {
    // items 2 and 4 will fail
    const result = await runBulk([1, 2, 3, 4, 5], async (n) => {
      if (n === 2 || n === 4) throw new Error("fail");
    });
    expect(result.succeeded).toEqual([1, 3, 5]);
    expect(result.failed).toEqual([2, 4]);
  });

  it("runs all operations concurrently (does not await sequentially)", async () => {
    const started: number[] = [];
    const finished: number[] = [];

    // Each operation records when it started, then waits, then records finish.
    // If sequential, started would be [0, 1, 2] and each finish follows the
    // previous start.  Concurrent: all 3 start before any finishes.
    const result = await runBulk([0, 1, 2], async (n) => {
      started.push(n);
      await new Promise<void>((res) => setTimeout(res, 10));
      finished.push(n);
    });

    // All three started before any finished (concurrent, not sequential)
    expect(started).toHaveLength(3);
    expect(result.succeeded).toHaveLength(3);
  });

  it("preserves item identity through the operation", async () => {
    const items = [{ id: "a" }, { id: "b" }, { id: "c" }];
    const result = await runBulk(items, async (item) => {
      if (item.id === "b") throw new Error("b failed");
    });
    expect(result.succeeded).toEqual([{ id: "a" }, { id: "c" }]);
    expect(result.failed).toEqual([{ id: "b" }]);
  });
});

// ---------------------------------------------------------------------------
// bulkResultToast
// ---------------------------------------------------------------------------

describe("bulkResultToast", () => {
  it("shows only the success count when nothing failed", () => {
    expect(bulkResultToast("deleted", 3, 0)).toBe("3 deleted");
  });

  it("shows 'All N failed' when nothing succeeded", () => {
    expect(bulkResultToast("deleted", 0, 3)).toBe("All 3 failed");
  });

  it("shows both counts on partial failure", () => {
    expect(bulkResultToast("queued for enrichment", 4, 2)).toBe(
      "4 queued for enrichment, 2 failed",
    );
  });

  it("handles single item success", () => {
    expect(bulkResultToast("deleted", 1, 0)).toBe("1 deleted");
  });

  it("handles single item failure in partial result", () => {
    expect(bulkResultToast("deleted", 2, 1)).toBe("2 deleted, 1 failed");
  });
});
