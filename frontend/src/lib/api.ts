/**
 * Typed client for the FastAPI backend.
 *
 * WHY every call runs in the browser (Client Components) rather than in
 * Server Components: the backend is a SEPARATE service authenticated with
 * a bearer token, and this app stores that token in localStorage -- a
 * browser-only API a Server Component cannot read. Fetching server-side
 * would mean moving the token into an httpOnly cookie and proxying every
 * request through Next's own server, which buys nothing here (the backend
 * already enforces auth) and costs an extra hop plus a second place for
 * auth logic to drift. If this ever needs SEO or server-rendered data,
 * that cookie-and-proxy design is the thing to revisit.
 */

import type {
  AuthToken,
  CtdBuildResponse,
  EctdBuildResponse,
  EctdValidationResponse,
  Narrative,
  Product,
  Project,
  ReadinessResponse,
  SectionSpec,
  Sequence,
  Vocabularies,
} from "@/lib/types";

/**
 * WHY NEXT_PUBLIC_ and not a server-only var: this value is read by
 * browser code, so it must be inlined at build time. It is a public URL,
 * not a secret -- nothing sensitive belongs in a NEXT_PUBLIC_ var.
 */
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const TOKEN_STORAGE_KEY = "dossier.access_token";

/** Thrown for any non-2xx response, carrying the status so callers can
 * distinguish "not logged in" (401) from a real failure. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function storeToken(token: string): void {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearStoredToken(): void {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

/**
 * The backend wraps errors as `{"error": {"code": ..., "message": ...}}`
 * (see backend/app/api/errors.py) but FastAPI's own validation errors use
 * `{"detail": ...}`. Try both before falling back to the status text, so a
 * user never sees a bare "500".
 */
async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.error?.message === "string") return body.error.message;
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      return body.detail
        .map((d: { msg?: string }) => d.msg ?? "invalid input")
        .join("; ");
    }
  } catch {
    // Response had no JSON body -- fall through to the status text.
  }
  return response.statusText || `Request failed (${response.status})`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    throw new ApiError(response.status, await extractErrorMessage(response));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  /**
   * WHY form-encoded, not JSON: the backend's /auth/login uses FastAPI's
   * OAuth2PasswordRequestForm, which is specified to read form fields --
   * and its username field is where this app's email goes.
   */
  async login(email: string, password: string): Promise<AuthToken> {
    const body = new URLSearchParams({ username: email, password });
    const response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!response.ok) {
      throw new ApiError(response.status, await extractErrorMessage(response));
    }
    return (await response.json()) as AuthToken;
  },

  register(email: string, password: string) {
    return request<{ id: string; email: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  listProjects() {
    return request<Project[]>("/projects");
  },

  getProject(projectId: string) {
    return request<Project>(`/projects/${projectId}`);
  },

  getReadiness(projectId: string) {
    return request<ReadinessResponse>(`/projects/${projectId}/readiness`);
  },

  listSequences(projectId: string) {
    return request<Sequence[]>(`/projects/${projectId}/sequences`);
  },

  /** Controlled vocabularies for every dropdown -- see lib/types.ts. */
  getEnums() {
    return request<Vocabularies>("/enums");
  },

  createProduct(payload: Record<string, unknown>) {
    return request<Product>("/products", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getProduct(productId: string) {
    return request<Product>(`/products/${productId}`);
  },

  /**
   * The six Product-child collections all share one URL shape and one
   * verb set, because the backend builds their routers from a single
   * factory (app/api/routers/product_children.py). Mirroring that with
   * one parameterised method instead of six near-identical ones keeps the
   * two sides the same shape -- add a resource there, and nothing here
   * needs to change.
   */
  createProductChild(
    productId: string,
    resource: ProductChildResource,
    payload: Record<string, unknown>,
  ) {
    return request<{ id: string }>(`/products/${productId}/${resource}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  deleteProductChild(
    productId: string,
    resource: ProductChildResource,
    childId: string,
  ) {
    return request<void>(`/products/${productId}/${resource}/${childId}`, {
      method: "DELETE",
    });
  },

  createProject(payload: {
    name: string;
    region: string;
    product_id: string;
  }) {
    return request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /** Which sections exist and which narrative slots each offers. */
  getSections() {
    return request<SectionSpec[]>("/sections");
  },

  // ---- narrative review (P05) ------------------------------------------
  //
  // The `:generate` / `:approve` / `:edit` suffixes are the backend's
  // deliberate "custom method" convention: these are state transitions
  // with side effects (an LLM call, a human review decision), not CRUD on
  // a resource. Kept verbatim here rather than prettified into REST verbs.

  listNarratives(projectId: string, section: string, slot: string) {
    return request<Narrative[]>(
      `/projects/${projectId}/sections/${section}/narrative/${slot}`,
    );
  },

  generateNarrative(projectId: string, section: string, slot: string) {
    return request<{ narrative: Narrative; warnings: string[] }>(
      `/projects/${projectId}/sections/${section}/narrative/${slot}:generate`,
      { method: "POST" },
    );
  },

  approveNarrative(
    projectId: string,
    section: string,
    slot: string,
    narrativeId: string,
  ) {
    return request<Narrative>(
      `/projects/${projectId}/sections/${section}/narrative/${slot}/${narrativeId}:approve`,
      { method: "POST" },
    );
  },

  editNarrative(
    projectId: string,
    section: string,
    slot: string,
    narrativeId: string,
    text: string,
  ) {
    return request<Narrative>(
      `/projects/${projectId}/sections/${section}/narrative/${slot}/${narrativeId}:edit`,
      { method: "POST", body: JSON.stringify({ text }) },
    );
  },

  // ---- build + validate -------------------------------------------------

  buildCtd(projectId: string) {
    return request<CtdBuildResponse>(`/projects/${projectId}/build/ctd`, {
      method: "POST",
    });
  },

  createSequence(projectId: string, description?: string) {
    return request<Sequence>(`/projects/${projectId}/sequences`, {
      method: "POST",
      body: JSON.stringify({ description: description ?? null }),
    });
  },

  buildEctd(projectId: string, sequenceId: string) {
    return request<EctdBuildResponse>(
      `/projects/${projectId}/build/ectd?sequence_id=${sequenceId}`,
      { method: "POST" },
    );
  },

  validateEctd(projectId: string, sequenceId: string) {
    return request<EctdValidationResponse>(
      `/projects/${projectId}/validate/ectd?sequence_id=${sequenceId}`,
      { method: "POST" },
    );
  },

  /**
   * Download a built package, saving it with its real filename.
   *
   * WHY fetch-then-save rather than pointing an <a href> at the endpoint:
   * a plain link or window.open() cannot carry an Authorization header,
   * so the obvious version would need the token in the query string --
   * and tokens in URLs leak into server logs, browser history, and
   * referrers. Fetching the bytes with the normal auth header and handing
   * the browser a blob keeps the credential where it belongs, at the cost
   * of holding the zip in memory (fine at dossier scale; revisit with a
   * one-time signed URL if packages ever get large).
   */
  async downloadArtifact(projectId: string, key: string): Promise<void> {
    const token = getStoredToken();
    const headers = new Headers();
    if (token) headers.set("Authorization", `Bearer ${token}`);

    const params = new URLSearchParams({ key });
    const response = await fetch(
      `${API_BASE_URL}/projects/${projectId}/artifacts?${params}`,
      { headers },
    );
    if (!response.ok) {
      throw new ApiError(response.status, await extractErrorMessage(response));
    }

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = key.split("/").pop() ?? "package.zip";
    document.body.appendChild(link);
    link.click();
    link.remove();
    // Revoking immediately would race the browser's save on some engines.
    setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);
  },
};

/** The child collections mounted under /products/{id}/... */
export type ProductChildResource =
  | "manufacturers"
  | "apis"
  | "excipients"
  | "packaging"
  | "stability"
  | "clinical";
