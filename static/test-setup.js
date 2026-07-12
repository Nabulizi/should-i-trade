// Prevent app.js init code (load(), connectSSE(), etc.) from running during tests.
globalThis.__TESTING__ = true;

// Node >= 25 ships an experimental global localStorage that shadows jsdom's,
// but it is undefined without --localstorage-file. Provide an in-memory stub
// so `npm test` behaves the same on Node 20 (CI) and newer local runtimes.
if (!globalThis.localStorage) {
  const store = new Map();
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (k) => (store.has(String(k)) ? store.get(String(k)) : null),
      setItem: (k, v) => store.set(String(k), String(v)),
      removeItem: (k) => store.delete(String(k)),
      clear: () => store.clear(),
      key: (i) => [...store.keys()][i] ?? null,
      get length() { return store.size; },
    },
  });
}
