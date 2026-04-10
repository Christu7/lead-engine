import "@testing-library/jest-dom";

// ---------------------------------------------------------------------------
// Storage mocks
//
// Vitest 3.x passes an internal `--localstorage-file` option to jsdom that
// may be invalid in some environments, resulting in a localStorage / session-
// Storage object whose methods are non-functions.  Override both with proper
// in-memory implementations so tests can call setItem / getItem / clear.
// ---------------------------------------------------------------------------

class StorageMock implements Storage {
  private store = new Map<string, string>();

  get length() {
    return this.store.size;
  }

  clear() {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null;
  }

  key(index: number): string | null {
    return [...this.store.keys()][index] ?? null;
  }

  removeItem(key: string) {
    this.store.delete(key);
  }

  setItem(key: string, value: string) {
    this.store.set(key, value);
  }
}

Object.defineProperty(window, "localStorage", {
  value: new StorageMock(),
  writable: true,
  configurable: true,
});

Object.defineProperty(window, "sessionStorage", {
  value: new StorageMock(),
  writable: true,
  configurable: true,
});
