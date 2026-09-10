import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { AuthGuard } from "@/components/AuthGuard";
import { AuthProvider } from "@/lib/auth";
import { storeToken, getStoredToken } from "@/lib/api";

// next/navigation's router only exists inside a Next runtime, so the one
// thing this test asserts on -- "did the app navigate to /login" -- has to
// be stubbed. `replace` is the method AuthGuard uses.
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
}));

function mockFetch(response: { ok: boolean; status: number; json?: unknown }) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: response.ok,
      status: response.status,
      statusText: "",
      json: async () => response.json ?? {},
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  replace.mockClear();
});

describe("an expired session", () => {
  /**
   * The integration the unit tests cannot prove on their own. Each link in
   * the chain is cheap to test alone and the chain still failed to exist:
   * clearing localStorage without notifying leaves useSyncExternalStore
   * holding the old value, so the guard goes on believing the user is
   * signed in and nobody is ever sent to the login page.
   */
  it("sends the user to the login page instead of rendering the guarded page", async () => {
    storeToken("expired-token");
    // What GET /auth/me answers for a token past its hour.
    mockFetch({
      ok: false,
      status: 401,
      json: { error: { code: 401, message: "Could not validate credentials" } },
    });

    render(
      <AuthProvider>
        <AuthGuard>
          <p>the wizard</p>
        </AuthGuard>
      </AuthProvider>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(getStoredToken()).toBeNull();
    expect(screen.queryByText("the wizard")).toBeNull();
  });

  it("leaves a working session alone", async () => {
    storeToken("good-token");
    mockFetch({
      ok: true,
      status: 200,
      json: { id: "u1", email: "a@b.c", is_active: true, role: "user" },
    });

    render(
      <AuthProvider>
        <AuthGuard>
          <p>the wizard</p>
        </AuthGuard>
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByText("the wizard")).toBeDefined());
    expect(replace).not.toHaveBeenCalled();
    expect(getStoredToken()).toBe("good-token");
  });
});
