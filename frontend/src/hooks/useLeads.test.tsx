import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { useLeads } from "./useLeads";
import { fetchLeads } from "../api/leads";

// ---------------------------------------------------------------------------
// Module-level mock — vi.mock is hoisted so it intercepts the import inside
// useLeads.ts rather than just replacing the re-exported symbol.
// ---------------------------------------------------------------------------

vi.mock("../api/leads", () => ({
  fetchLeads: vi.fn(),
}));

const mockFetchLeads = vi.mocked(fetchLeads);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

function makeLeadPage(id: number, email: string) {
  return {
    items: [
      {
        id,
        email,
        name: `Lead ${id}`,
        status: "new",
        score: 0,
        enrichment_status: "pending",
        source: "test",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        client_id: id,
      },
    ],
    total: 1,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useLeads — clientVersion", () => {
  beforeEach(() => {
    mockFetchLeads.mockReset();
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("fetches on initial render", async () => {
    mockFetchLeads.mockResolvedValueOnce(makeLeadPage(1, "initial@example.com"));

    const { result } = renderHook(() => useLeads(0), { wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(mockFetchLeads).toHaveBeenCalledTimes(1);
    expect(result.current.items[0].email).toBe("initial@example.com");
  });

  it("refetches when clientVersion changes", async () => {
    mockFetchLeads
      .mockResolvedValueOnce(makeLeadPage(1, "client1@example.com"))
      .mockResolvedValueOnce(makeLeadPage(2, "client2@example.com"));

    const { result, rerender } = renderHook(
      ({ cv }: { cv: number }) => useLeads(cv),
      { wrapper, initialProps: { cv: 0 } },
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items[0].email).toBe("client1@example.com");

    rerender({ cv: 1 });

    await waitFor(() => {
      expect(result.current.items[0].email).toBe("client2@example.com");
    });

    expect(mockFetchLeads).toHaveBeenCalledTimes(2);
  });

  it("ignores stale response from old workspace when clientVersion changes mid-fetch", async () => {
    // client-0 fetch is slow — we control when it resolves
    let resolveClient0!: (value: ReturnType<typeof makeLeadPage>) => void;
    const client0Promise = new Promise<ReturnType<typeof makeLeadPage>>(
      (resolve) => {
        resolveClient0 = resolve;
      },
    );

    mockFetchLeads
      .mockReturnValueOnce(client0Promise) // first call: hangs until we resolve it
      .mockResolvedValueOnce(makeLeadPage(2, "client2@example.com")); // second call: resolves fast

    const { result, rerender } = renderHook(
      ({ cv }: { cv: number }) => useLeads(cv),
      { wrapper, initialProps: { cv: 0 } },
    );

    // client-0 fetch is in flight.  Switch workspace before it resolves.
    rerender({ cv: 1 });

    // client-1 fetch resolves fast — wait for it.
    await waitFor(() => {
      expect(result.current.items[0]?.email).toBe("client2@example.com");
    });

    // Now let the stale client-0 response arrive.
    act(() => {
      resolveClient0(makeLeadPage(1, "stale-client1@example.com"));
    });

    // Allow one async tick to settle.
    await new Promise((r) => setTimeout(r, 20));

    // Stale data must NOT overwrite the current workspace's data.
    expect(result.current.items[0].email).toBe("client2@example.com");
  });

  it("sets loading=true at the start of each refetch triggered by clientVersion", async () => {
    mockFetchLeads
      .mockResolvedValueOnce(makeLeadPage(1, "a@example.com"))
      .mockResolvedValueOnce(makeLeadPage(2, "b@example.com"));

    const { result, rerender } = renderHook(
      ({ cv }: { cv: number }) => useLeads(cv),
      { wrapper, initialProps: { cv: 0 } },
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    rerender({ cv: 1 });
    expect(result.current.loading).toBe(true);

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items[0].email).toBe("b@example.com");
  });
});
