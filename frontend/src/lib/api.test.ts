import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  api,
  clearStoredToken,
  getSessionExpired,
  getStoredToken,
  storeToken,
  subscribeToAuthStore,
} from "@/lib/api";

function mockFetchOnce(response: {
  ok?: boolean;
  status?: number;
  json?: unknown;
  statusText?: string;
}) {
  const spy = vi.fn().mockResolvedValue({
    ok: response.ok ?? true,
    status: response.status ?? 200,
    statusText: response.statusText ?? "OK",
    json: async () => response.json ?? {},
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("token storage", () => {
  it("round-trips a token and clears it", () => {
    expect(getStoredToken()).toBeNull();
    storeToken("abc123");
    expect(getStoredToken()).toBe("abc123");
    clearStoredToken();
    expect(getStoredToken()).toBeNull();
  });
});

describe("request auth", () => {
  it("attaches the stored bearer token", async () => {
    storeToken("tok-42");
    const spy = mockFetchOnce({ json: [] });

    await api.listProjects();

    const headers = spy.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer tok-42");
  });

  it("omits the header entirely when signed out", async () => {
    const spy = mockFetchOnce({ json: [] });

    await api.listProjects();

    const headers = spy.mock.calls[0][1].headers as Headers;
    expect(headers.has("Authorization")).toBe(false);
  });
});

describe("error handling", () => {
  it("surfaces the backend's error envelope message", async () => {
    // The shape backend/app/api/errors.py normalizes everything to.
    mockFetchOnce({
      ok: false,
      status: 404,
      json: { error: { code: 404, message: "Project not found" } },
    });

    await expect(api.getProject("nope")).rejects.toThrowError(
      new ApiError(404, "Project not found"),
    );
  });

  it("falls back to FastAPI's own detail shape", async () => {
    mockFetchOnce({ ok: false, status: 401, json: { detail: "Not authenticated" } });

    await expect(api.listProjects()).rejects.toMatchObject({
      status: 401,
      message: "Not authenticated",
    });
  });

  it("never throws a bare status when the body has no JSON", async () => {
    const spy = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: async () => {
        throw new Error("not json");
      },
    });
    vi.stubGlobal("fetch", spy);

    await expect(api.listProjects()).rejects.toMatchObject({
      message: "Internal Server Error",
    });
  });
});

describe("401 ends the session", () => {
  // The bug these pin: a token that has EXPIRED is indistinguishable from
  // a good one to AuthGuard, which only checks that a token exists. With
  // /enums served unauthenticated, a dead session still rendered a fully
  // populated wizard and only announced itself as "Could not validate
  // credentials" when the user pressed Save.
  it("clears the stored token", async () => {
    storeToken("expired-token");
    mockFetchOnce({
      ok: false,
      status: 401,
      json: { error: { code: 401, message: "Could not validate credentials" } },
    });

    await expect(api.listProjects()).rejects.toMatchObject({ status: 401 });

    expect(getStoredToken()).toBeNull();
  });

  it("notifies subscribers, which is what actually triggers the redirect", async () => {
    // Clearing localStorage is not enough on its own: useSyncExternalStore
    // only re-reads when a subscriber fires, and the browser's `storage`
    // event never fires in the tab that made the change.
    storeToken("expired-token");
    const onChange = vi.fn();
    const unsubscribe = subscribeToAuthStore(onChange);
    mockFetchOnce({ ok: false, status: 401, json: {} });

    await expect(api.listProjects()).rejects.toMatchObject({ status: 401 });

    expect(onChange).toHaveBeenCalled();
    unsubscribe();
  });

  it("leaves the token alone on any other failure", async () => {
    // A 409 from a refused export, a 500, a 404 -- none of these say
    // anything about the credential, and signing the user out of a long
    // wizard over one is the cure being worse than the disease.
    storeToken("good-token");
    mockFetchOnce({
      ok: false,
      status: 409,
      json: { error: { code: 409, message: "Export blocked" } },
    });

    await expect(api.buildCtd("p1")).rejects.toMatchObject({ status: 409 });

    expect(getStoredToken()).toBe("good-token");
  });

  it("flags the expiry, so the login page can say what happened", async () => {
    storeToken("expired-token");
    mockFetchOnce({ ok: false, status: 401, json: {} });

    await expect(api.listProjects()).rejects.toMatchObject({ status: 401 });

    expect(getSessionExpired()).toBe(true);
  });

  it("does not claim a session expired when there was never a token", async () => {
    // A 401 while already signed out is just an unauthenticated call.
    // Telling that user their session expired would be a lie.
    mockFetchOnce({ ok: false, status: 401, json: {} });

    await expect(api.listProjects()).rejects.toMatchObject({ status: 401 });

    expect(getSessionExpired()).toBe(false);
  });

  it("does not treat a rejected login as an expired session", async () => {
    // A wrong password answers 401 too. Routing it through the shared
    // handler would clear a token the failure says nothing about.
    storeToken("good-token");
    mockFetchOnce({
      ok: false,
      status: 401,
      json: { error: { code: 401, message: "Incorrect email or password" } },
    });

    await expect(api.login("user@example.com", "wrong")).rejects.toMatchObject({
      status: 401,
    });

    expect(getStoredToken()).toBe("good-token");
    expect(getSessionExpired()).toBe(false);
  });
});

describe("login", () => {
  it("posts form-encoded credentials, since the backend uses OAuth2PasswordRequestForm", async () => {
    const spy = mockFetchOnce({ json: { access_token: "t", token_type: "bearer" } });

    await api.login("user@example.com", "pw");

    const [, init] = spy.mock.calls[0];
    expect(init.headers["Content-Type"]).toBe(
      "application/x-www-form-urlencoded",
    );
    // The spec names the field "username"; this app puts the email there.
    expect(String(init.body)).toContain("username=user%40example.com");
  });
});
