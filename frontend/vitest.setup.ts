import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// React Testing Library mounts into a shared document; without this, each
// test sees the previous test's DOM still attached.
afterEach(() => {
  cleanup();
  window.localStorage.clear();
  // The "your session expired" flag lives here, and a test that leaves one
  // behind would hand the next test a session it never ended.
  window.sessionStorage.clear();
});
