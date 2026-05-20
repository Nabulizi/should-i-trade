// Prevent app.js init code (load(), connectSSE(), etc.) from running during tests.
globalThis.__TESTING__ = true;
