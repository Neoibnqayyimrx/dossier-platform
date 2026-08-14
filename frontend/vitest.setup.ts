import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// React Testing Library mounts into a shared document; without this, each
// test sees the previous test's DOM still attached.
afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
