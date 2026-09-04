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
  Applicant,
  AuthToken,
  CtdBuildResponse,
  EctdBuildResponse,
  EctdValidationResponse,
  Declaration,
  Narrative,
  Product,
  Project,
  RegionProfile,
  ReadinessResponse,
  SectionSpec,
  SectionStatus,
  Sequence,
  SpecificationTest,
  User,
  ValidationOverride,
  UserRole,
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

  /** Who the current bearer token belongs to, looked up fresh every call
   * (see backend/app/api/routers/auth.py's me() WHY -- a role change
   * takes effect the next time this is called, not just at next login). */
  me() {
    return request<User>("/auth/me");
  },

  // ---- admin-only user management (P14b) ---------------------------------

  listUsers() {
    return request<User[]>("/admin/users");
  },

  updateUser(userId: string, payload: { role?: UserRole; is_active?: boolean }) {
    return request<User>(`/admin/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  /** Which Module 1 documents this region demands. Served by the backend
   * so the UI can never ask for a different set than R13/R16 enforce
   * (see app/api/routers/regions.py). */
  listRegionProfiles() {
    return request<RegionProfile[]>("/regions");
  },

  // ---- Module 1 (P15) ----------------------------------------------------

  listApplicants() {
    return request<Applicant[]>("/applicants");
  },

  createApplicant(payload: Record<string, unknown>) {
    return request<Applicant>("/applicants", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  createDeclaration(projectId: string, payload: Record<string, unknown>) {
    return request<Declaration>(`/projects/${projectId}/declarations`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  updateDeclaration(
    projectId: string,
    declarationId: string,
    payload: Record<string, unknown>,
  ) {
    return request<Declaration>(
      `/projects/${projectId}/declarations/${declarationId}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    );
  },

  deleteDeclaration(projectId: string, declarationId: string) {
    return request<void>(`/projects/${projectId}/declarations/${declarationId}`, {
      method: "DELETE",
    });
  },

  updateProject(projectId: string, payload: Record<string, unknown>) {
    return request<Project>(`/projects/${projectId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  // ---- validation overrides (P15c) ---------------------------------------

  listOverrides(projectId: string) {
    return request<ValidationOverride[]>(
      `/projects/${projectId}/validation-overrides`,
    );
  },

  createOverride(projectId: string, ruleId: string, reason: string) {
    return request<ValidationOverride>(
      `/projects/${projectId}/validation-overrides`,
      {
        method: "POST",
        body: JSON.stringify({ rule_id: ruleId, reason }),
      },
    );
  },

  withdrawOverride(projectId: string, overrideId: string) {
    return request<ValidationOverride>(
      `/projects/${projectId}/validation-overrides/${overrideId}:withdraw`,
      { method: "POST" },
    );
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

  /**
   * Specification rows hang off an ACTIVE INGREDIENT, not a product --
   * 3.2.S is repeated per drug substance, so each active has its own
   * specification. Same factory on the backend, different parent.
   */
  createSpecificationTest(
    apiId: string,
    payload: {
      test_name: string;
      method: string;
      acceptance_criterion: string;
      sort_order: number;
    },
  ) {
    return request<SpecificationTest>(`/apis/${apiId}/specification`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  listSpecificationTests(apiId: string) {
    return request<SpecificationTest[]>(`/apis/${apiId}/specification`);
  },

  deleteSpecificationTest(apiId: string, rowId: string) {
    return request<void>(`/apis/${apiId}/specification/${rowId}`, {
      method: "DELETE",
    });
  },

  createProject(payload: {
    name: string;
    region: string;
    /** P17: how much of the CTD this filing owes. Optional here because
     * the backend defaults it to the one scope the platform was built
     * against; sent explicitly by the wizard so the choice is the filer's. */
    submission_type?: string;
    product_id: string;
    /** Optional at creation: a project can exist before anyone has said
     * who is filing. Rule R14 is what makes it required before export,
     * not the schema. */
    applicant_id?: string | null;
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

  // ---- applicability (P17) ---------------------------------------------

  /** Every leaf this project's submission type declares, with its status. */
  getSectionStatus(projectId: string) {
    return request<SectionStatus[]>(`/projects/${projectId}/section-status`);
  },

  /**
   * Answer one or more conditional sections. A MERGE, not a replace --
   * sending the whole map on every click would let two people editing one
   * project silently undo each other. `null` retracts an answer, which is
   * not the same as `false` (a positive "does not apply" that files a
   * statement). The recomputed list comes back, because answering "no"
   * does not merely record a preference: it adds a leaf to the package.
   */
  answerConditions(projectId: string, answers: Record<string, boolean | null>) {
    return request<SectionStatus[]>(`/projects/${projectId}/conditions`, {
      method: "PATCH",
      body: JSON.stringify({ answers }),
    });
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
  | "clinical"
  | "batch-formula"
  | "certificates";
