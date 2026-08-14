import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  api,
  clearStoredToken,
  getStoredToken,
  storeToken,
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
