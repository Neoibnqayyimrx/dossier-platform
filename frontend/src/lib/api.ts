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

import { SPECIFICATION_PARENT } from "@/lib/types";
import type {
  Applicant,
  AuthToken,
  CtdBuildResponse,
  EctdBuildResponse,
  EctdValidationResponse,
  Declaration,
  Narrative,
  Product,
  ProductInformation,
  ProductInformationWrite,
  Project,
  RegionProfile,
  ReadinessResponse,
  SectionSpec,
  SectionDocument,
  SectionStatus,
  Sequence,
  BatchAnalysis,
  BatchAnalysisResult,
  BioequivalenceResult,
  BioequivalenceStudy,
  Biowaiver,
  PKParameter,
  ReferenceProduct,
  SpecificationOwnerKind,
  SpecificationTest,
  StabilityOwnerKind,
  StabilityResult,
  StabilityStudy,
  ThreeWayComparison,
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
/** One blocking finding from a refused export (P18). */
export interface BlockingFinding {
  rule_id: string;
  /** The leaf that is holding the build up, when the rule names one. */
  section: string | null;
  message: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    /**
     * P18: which leaves refused the export. Present only on the 409 from a
     * build — everything else leaves it empty, so callers that only read
     * `message` are unaffected. This is what lets the build screen say
     * "these four leaves are waiting on a document" instead of printing a
     * paragraph the user has to translate back into a to-do list.
     */
    public readonly blocking: BlockingFinding[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Subscribers to the token store.
 *
 * WHY this lives here rather than in lib/auth.tsx, next to the React hook
 * that reads it: localStorage fires its own `storage` event only in OTHER
 * tabs, never the one that made the change, so a same-tab write has to
 * announce itself by hand. Keeping the listener set beside the two
 * functions that can write means every write notifies -- including the
 * sign-out below, which is triggered by a fetch RESPONSE rather than by a
 * click, and so has no component around to do it. The alternative
 * (auth.tsx exports `notify`, this module calls it) is an import cycle:
 * auth.tsx already imports this file.
 */
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of listeners) listener();
}

/**
 * The `subscribe` half of every useSyncExternalStore that reads this
 * module -- the token itself, and the "your session expired" flag below.
 * Listens for the cross-tab `storage` event as well as same-tab writes,
 * which is what makes signing out in one tab sign out the rest.
 */
export function subscribeToAuthStore(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  window.addEventListener("storage", onStoreChange);
  return () => {
    listeners.delete(onStoreChange);
    window.removeEventListener("storage", onStoreChange);
  };
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

// WHY the `window` guard on the writers too, when only the reader used to
// need one: clearStoredToken is now reachable from any failed request, so
// it must be a no-op rather than a crash if a call ever runs where there
// is no browser.
export function storeToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  notify();
}

export function clearStoredToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  notify();
}

const SESSION_EXPIRED_KEY = "dossier.session_expired";

/**
 * Record that the session ended ON ITS OWN, so the login page can say so
 * rather than leaving the user to work out why they are suddenly back
 * here in the middle of a form.
 *
 * WHY sessionStorage and not a module variable: the redirect is a
 * client-side navigation today, but someone who reloads a guarded URL
 * carrying a stale token gets a full page load, and a module variable
 * does not survive one. WHY sessionStorage and not localStorage: this is
 * a note about THIS tab's interrupted work, and it should not still be
 * waiting in a window opened tomorrow.
 *
 * Never set by logout(): a person who signed out on purpose does not need
 * to be told their session ended.
 */
function markSessionExpired(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(SESSION_EXPIRED_KEY, "1");
  notify();
}

/**
 * Whether the last session ended by itself. A PURE read -- it does not
 * clear the flag.
 *
 * WHY reading and clearing are two functions when one call site wants
 * both: this is the `getSnapshot` of a useSyncExternalStore, and React
 * calls it during render, more than once, whenever it likes. A snapshot
 * that mutated the thing it samples would clear the flag on the render
 * that displays it and answer differently the next time it was asked.
 * Clearing is a separate, deliberate act -- see clearSessionExpired.
 */
export function getSessionExpired(): boolean {
  if (typeof window === "undefined") return false;
  return window.sessionStorage.getItem(SESSION_EXPIRED_KEY) !== null;
}

/** The story is over once the user is back in. Called on a successful
 * sign-in, which is an event, not a render. */
export function clearSessionExpired(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(SESSION_EXPIRED_KEY);
  notify();
}

/**
 * The backend wraps errors as `{"error": {"code": ..., "message": ...}}`
 * (see backend/app/api/errors.py) but FastAPI's own validation errors use
 * `{"detail": ...}`. Try both before falling back to the status text, so a
 * user never sees a bare "500".
 */
async function extractError(
  response: Response,
): Promise<{ message: string; blocking: BlockingFinding[] }> {
  try {
    const body = await response.json();
    const blocking: BlockingFinding[] = Array.isArray(body?.error?.blocking)
      ? body.error.blocking
      : [];
    if (typeof body?.error?.message === "string") {
      return { message: body.error.message, blocking };
    }
    if (typeof body?.detail === "string") {
      return { message: body.detail, blocking };
    }
    if (Array.isArray(body?.detail)) {
      return {
        message: body.detail
          .map((d: { msg?: string }) => d.msg ?? "invalid input")
          .join("; "),
        blocking,
      };
    }
  } catch {
    // Response had no JSON body -- fall through to the status text.
  }
  return {
    message: response.statusText || `Request failed (${response.status})`,
    blocking: [],
  };
}

/**
 * Turn a non-2xx response into the ApiError callers catch -- and, on a
 * 401, end the session first.
 *
 * WHY the sign-out belongs here rather than in each caller: a 401 means
 * the token this request just carried is expired, revoked, or issued to a
 * user who no longer exists. Nothing a retry can fix, and the only honest
 * state left is "signed out". Without this, an expired token was INVISIBLE
 * until the first write: AuthGuard checks that a token EXISTS, not that it
 * works, and /enums is public, so a wizard whose session had died still
 * rendered with every dropdown filled -- and then answered the Save button
 * with "Could not validate credentials", backend wording that means
 * nothing to a filer halfway through a form.
 *
 * Clearing the token notifies the token store, which flips the auth status
 * to "anonymous", which is what AuthGuard already redirects on. That is
 * the whole mechanism -- no new routing, no new state.
 *
 * NOT used by login(): a wrong password is a 401 too, and it must not be
 * dressed up as an expired session. That call builds its own error.
 */
async function toApiError(response: Response): Promise<ApiError> {
  if (response.status === 401) {
    // Only a token that EXISTED and was refused means a session ended. A
    // 401 while already signed out is just an unauthenticated call, and
    // announcing "your session expired" for one would be a lie.
    if (getStoredToken() !== null) markSessionExpired();
    clearStoredToken();
  }
  const failure = await extractError(response);
  return new ApiError(response.status, failure.message, failure.blocking);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  // P18: FormData must NOT get a Content-Type here. The browser sets its
  // own `multipart/form-data; boundary=...`, and the boundary is generated
  // per request — stamping "application/json" on a file upload produces a
  // body the server cannot parse, with a 422 that blames the file rather
  // than the header.
  if (
    init.body &&
    !headers.has("Content-Type") &&
    !(init.body instanceof FormData)
  ) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) throw await toApiError(response);
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
    // WHY this builds its own error instead of calling toApiError: a wrong
    // password answers 401 as well, and routing it through the shared
    // handler would clear a token that has nothing to do with the failure
    // and report a bad credential as an expired session.
    if (!response.ok) {
      const failure = await extractError(response);
      throw new ApiError(response.status, failure.message, failure.blocking);
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
   * P23 -- the SmPC / label / leaflet content.
   *
   * A 1:1 resource, so there is no create/list/delete trio: `PUT` is
   * create-or-replace, which is the honest verb for a thing there is
   * exactly one of. Replace, not merge -- the sections on screen ARE the
   * SmPC, so a contraindication the filer deleted has to be gone from the
   * leaflet too.
   *
   * The payload type deliberately cannot express a shelf life. The
   * backend answers 422 on one anyway (it forbids extra fields rather than
   * ignoring them), so this is the two layers saying the same thing.
   */
  getProductInformation(productId: string) {
    return request<ProductInformation>(
      `/products/${productId}/product-information`,
    );
  },

  saveProductInformation(
    productId: string,
    payload: Partial<ProductInformationWrite>,
  ) {
    return request<ProductInformation>(
      `/products/${productId}/product-information`,
      { method: "PUT", body: JSON.stringify(payload) },
    );
  },

  /**
   * The three-way comparison, keyed by PROJECT rather than product: it
   * compares what three DOCUMENTS print, and a document belongs to a
   * filing (the marketing authorisation holder comes off the applicant).
   */
  compareProductInformation(projectId: string) {
    return request<ThreeWayComparison>(
      `/projects/${projectId}/product-information/comparison`,
    );
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
   * Specification rows hang off whichever thing they are a specification
   * OF -- an active ingredient (3.2.S.4.1), an excipient (3.2.P.4.1) or
   * the product itself (3.2.P.5.1). P20 made the backend mount ONE model
   * at three parents, so these three helpers take an owner kind and an id
   * rather than existing three times over.
   *
   * The owner is always in the PATH, never in the body: the backend's
   * ownership check is on the parent in the path, so that is the only
   * place an owner can be trusted to come from.
   */
  createSpecificationTest(
    owner: SpecificationOwnerKind,
    ownerId: string,
    payload: {
      test_name: string;
      method: string;
      acceptance_criterion: string;
      sort_order: number;
    },
  ) {
    return request<SpecificationTest>(
      `/${SPECIFICATION_PARENT[owner]}/${ownerId}/specification`,
      { method: "POST", body: JSON.stringify(payload) },
    );
  },

  listSpecificationTests(owner: SpecificationOwnerKind, ownerId: string) {
    return request<SpecificationTest[]>(
      `/${SPECIFICATION_PARENT[owner]}/${ownerId}/specification`,
    );
  },

  deleteSpecificationTest(
    owner: SpecificationOwnerKind,
    ownerId: string,
    rowId: string,
  ) {
    return request<void>(
      `/${SPECIFICATION_PARENT[owner]}/${ownerId}/specification/${rowId}`,
      { method: "DELETE" },
    );
  },

  /**
   * Batches (3.2.S.4.4 / 3.2.P.5.4). Only a drug substance or the finished
   * product can have them -- the CTD has no excipient batch-analysis leaf,
   * which is why the backend's BatchAnalysis declares the narrower
   * two-owner space.
   */
  listBatches(owner: "drug-substance" | "drug-product", ownerId: string) {
    return request<BatchAnalysis[]>(
      `/${SPECIFICATION_PARENT[owner]}/${ownerId}/batches`,
    );
  },

  createBatch(
    owner: "drug-substance" | "drug-product",
    ownerId: string,
    payload: {
      batch_number: string;
      manufacture_date?: string | null;
      batch_size?: string | null;
      purpose?: string | null;
    },
  ) {
    return request<BatchAnalysis>(
      `/${SPECIFICATION_PARENT[owner]}/${ownerId}/batches`,
      { method: "POST", body: JSON.stringify(payload) },
    );
  },

  deleteBatch(
    owner: "drug-substance" | "drug-product",
    ownerId: string,
    batchId: string,
  ) {
    return request<void>(
      `/${SPECIFICATION_PARENT[owner]}/${ownerId}/batches/${batchId}`,
      { method: "DELETE" },
    );
  },

  /** A result always names the specification test it answers. The backend
   * refuses one whose test belongs to a different material (422). */
  createBatchResult(
    batchId: string,
    payload: { specification_test_id: string; result: string; sort_order: number },
  ) {
    return request<BatchAnalysisResult>(`/batches/${batchId}/results`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  deleteBatchResult(batchId: string, resultId: string) {
    return request<void>(`/batches/${batchId}/results/${resultId}`, {
      method: "DELETE",
    });
  },

  /**
   * Stability studies (3.2.S.7 / 3.2.P.8). Mounted at two parents for the
   * same reason batches are: a study is a study OF the drug substance or
   * OF the finished product, and the CTD has no third place to file one.
   */
  listStabilityStudies(owner: StabilityOwnerKind, ownerId: string) {
    return request<StabilityStudy[]>(
      `/${SPECIFICATION_PARENT[owner]}/${ownerId}/stability`,
    );
  },

  createStabilityStudy(
    owner: StabilityOwnerKind,
    ownerId: string,
    payload: {
      study_type: string;
      condition: string;
      duration_months: number;
      batch_analysis_id?: string | null;
      packaging_id?: string | null;
      protocol?: string | null;
    },
  ) {
    return request<StabilityStudy>(
      `/${SPECIFICATION_PARENT[owner]}/${ownerId}/stability`,
      { method: "POST", body: JSON.stringify(payload) },
    );
  },

  deleteStabilityStudy(
    owner: StabilityOwnerKind,
    ownerId: string,
    studyId: string,
  ) {
    return request<void>(
      `/${SPECIFICATION_PARENT[owner]}/${ownerId}/stability/${studyId}`,
      { method: "DELETE" },
    );
  },

  /**
   * Replace a study's whole result set -- the grid's save, and where a
   * spreadsheet paste lands.
   *
   * A PUT rather than N POSTs, and the reason is the grid: forty cells
   * saved one request at a time is forty chances to half-save the table,
   * and a half-saved stability table is worse than none because it looks
   * complete. The backend validates the whole payload before deleting
   * anything, so a paste naming one unknown test leaves the existing
   * table exactly as it was.
   */
  replaceStabilityResults(
    studyId: string,
    results: Array<{
      specification_test_id: string;
      timepoint_months: number;
      result: string;
    }>,
  ) {
    return request<StabilityResult[]>(`/stability/${studyId}/results`, {
      method: "PUT",
      body: JSON.stringify(results),
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

  // ---- uploaded documents (P18) ----------------------------------------

  listDocuments(projectId: string) {
    return request<SectionDocument[]>(`/projects/${projectId}/documents`);
  },

  /**
   * Attach (or replace) the file at one leaf.
   *
   * PUT, because the leaf is the resource and holds exactly one document —
   * uploading twice replaces rather than accumulates. No Content-Type is
   * set: the browser must add its own multipart boundary, and setting the
   * header by hand omits it and produces a request the server cannot parse.
   */
  uploadDocument(
    projectId: string,
    sectionNumber: string,
    file: File,
    subjectSlug = "",
  ) {
    const body = new FormData();
    body.append("file", file);
    const query = subjectSlug
      ? `?subject_slug=${encodeURIComponent(subjectSlug)}`
      : "";
    return request<SectionDocument>(
      `/projects/${projectId}/documents/${encodeURIComponent(sectionNumber)}${query}`,
      { method: "PUT", body },
    );
  },

  deleteDocument(projectId: string, sectionNumber: string, subjectSlug = "") {
    const query = subjectSlug
      ? `?subject_slug=${encodeURIComponent(subjectSlug)}`
      : "";
    return request<void>(
      `/projects/${projectId}/documents/${encodeURIComponent(sectionNumber)}${query}`,
      { method: "DELETE" },
    );
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

  // ---- P22: bioequivalence ----------------------------------------------
  //
  // The three collections go through `createProductChild`/
  // `deleteProductChild` like every other product child -- they are on the
  // same factory on the backend, and adding a bespoke method per resource
  // is exactly what that factory exists to avoid. Only the RESULTS need
  // their own calls, because they are replaced as a set rather than added
  // a row at a time.

  listBioequivalenceStudies(productId: string) {
    return request<BioequivalenceStudy[]>(`/products/${productId}/bioequivalence`);
  },

  listReferenceProducts(productId: string) {
    return request<ReferenceProduct[]>(`/products/${productId}/reference-products`);
  },

  listBiowaivers(productId: string) {
    return request<Biowaiver[]>(`/products/${productId}/biowaivers`);
  },

  updateBioequivalenceStudy(
    productId: string,
    studyId: string,
    payload: Record<string, unknown>,
  ) {
    return request<BioequivalenceStudy>(
      `/products/${productId}/bioequivalence/${studyId}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    );
  },

  /**
   * Replace a study's whole result set.
   *
   * PUT, not three POSTs, and for the reason the backend router gives: a
   * study report states Cmax, AUC(0-t) and AUC(0-inf) together in one
   * table, and a study holding two of its three intervals is worse than
   * one holding none, because it looks answered.
   */
  replaceBioequivalenceResults(
    studyId: string,
    rows: Array<{
      parameter: PKParameter;
      geometric_mean_ratio: string | null;
      ci_lower: string;
      ci_upper: string;
      intra_subject_cv: string | null;
    }>,
  ) {
    return request<BioequivalenceResult[]>(`/bioequivalence/${studyId}/results`, {
      method: "PUT",
      body: JSON.stringify(rows),
    });
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
    // Its own fetch (see the WHY above), so the shared 401 handling has to
    // be asked for by name here rather than coming free from request().
    if (!response.ok) throw await toApiError(response);

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
  | "bioequivalence"
  | "reference-products"
  | "biowaivers"
  | "clinical"
  | "batch-formula"
  | "certificates";
