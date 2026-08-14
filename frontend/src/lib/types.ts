/**
 * TypeScript mirrors of the backend's Pydantic read schemas
 * (backend/app/schemas/*.py).
 *
 * WHY hand-written rather than generated from the OpenAPI spec: the
 * backend is the single source of truth either way, and a generator would
 * add a build step plus a large surface of unused types for the handful
 * of shapes this UI actually reads. If these drift, they drift loudly --
 * every consumer is typed. Revisit if the surface grows much past this.
 */

/** Matches backend/app/models/enums.py::Region. */
export type Region = "NAFDAC" | "FDA" | "EU";

/** Matches backend/app/validation/engine.py::Severity. */
export type Severity = "ERROR" | "WARNING" | "INFO" | "ADVISORY";

/**
 * Which validation layer produced a finding (P10). "data-rule" is P06's
 * deterministic data checks; the rest come from the eCTD report.
 */
export type FindingSource =
  | "data-rule"
  | "mechanical-ectd"
  | "external-validator"
  | "ai-reviewer";

export interface Finding {
  rule_id: string;
  severity: Severity;
  category: string;
  message: string;
  section: string | null;
  source: FindingSource;
}

export interface ReadinessResponse {
  is_exportable: boolean;
  findings: Finding[];
  overridden_rule_ids: string[];
}

export interface Sequence {
  id: string;
  project_id: string;
  number: string;
  description: string | null;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Product {
  id: string;
  brand_name: string;
  generic_name: string;
  dosage_form: string | null;
  shelf_life_months: number | null;
  storage_condition: string | null;
  pack_size: string | null;
  route_of_administration: string | null;
  registration_type: string | null;
  country: string | null;
  /** Derived on the server: one strength per API, joined (combination products). */
  strength_display: string;
  manufacturers: unknown[];
  apis: unknown[];
  excipients: unknown[];
  packaging: unknown[];
  stability: unknown[];
  clinical: unknown[];
  batch_formula: unknown[];
}

export interface Project {
  id: string;
  name: string;
  region: Region;
  product: Product;
  sequences: Sequence[];
  created_at: string;
  updated_at: string;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
}

/**
 * Matches backend/app/models/enums.py::NarrativeStatus.
 *
 * These are LOWERCASE because that is what the enum's `.value` is, and
 * Pydantic serializes the value. Getting this wrong is not a cosmetic
 * bug: an earlier version of this type declared them uppercase, so
 * `status === "APPROVED"` was never true and an approved narrative
 * displayed as "awaiting review" forever -- hiding a human sign-off and
 * inviting the reviewer to approve the same draft repeatedly. Compare
 * against these values; uppercase only for display.
 */
export type NarrativeStatus = "pending" | "approved" | "edited";

export interface Narrative {
  id: string;
  project_id: string;
  section_number: string;
  slot: string;
  model_name: string;
  /** The raw model output, kept for audit even after an edit. */
  output: string;
  warnings: string[];
  status: NarrativeStatus;
  /**
   * What actually reaches a rendered document. Set only by approve/edit,
   * which is why a PENDING draft can never reach a dossier.
   */
  final_text: string | null;
  /** The KB chunks retrieved for this generation — its citations. */
  sources: string[];
}

export interface SectionSpec {
  number: string;
  title: string;
  /** Empty for data-only sections (e.g. 1.2, the registration form). */
  narrative_slots: string[];
}

export interface CtdBuildResponse {
  storage_key: string;
  files: { path: string; md5: string }[];
}

export interface EctdBuildResponse {
  storage_key: string;
  sequence_number: string;
  operations: Record<string, string>;
}

export interface EctdValidationResponse {
  sequence_number: string;
  is_exportable: boolean;
  findings: Finding[];
}

/** One option in a controlled vocabulary served by GET /enums. */
export interface EnumOption {
  value: string;
  label: string;
}

/**
 * The controlled vocabularies, keyed by name. Deliberately typed as an
 * index signature rather than a fixed set of keys: the backend owns which
 * vocabularies exist (app/api/routers/enums.py), and a hard-coded key list
 * here would be the very duplication that endpoint exists to prevent.
 */
export type Vocabularies = Record<string, EnumOption[]>;

export interface Manufacturer {
  id: string;
  name: string;
  role: string;
  site_address: string | null;
  country: string | null;
  gmp_status: string | null;
}

export interface ActiveIngredient {
  id: string;
  inn_name: string;
  strength_value: number | null;
  strength_unit: string | null;
  salt_form: string | null;
  compendial_std: string | null;
  /** 3.2.S.4.1 — one row per test. A specification is a table, not a
   * sentence: each row is a commitment (test, method, acceptance
   * criterion) the manufacturer is held to at release and on stability. */
  specification: SpecificationTest[];
}

export interface SpecificationTest {
  id: string;
  test_name: string;
  /** A citation ("BP monograph", "USP <467>"), never monograph text —
   * pharmacopoeias are copyrighted. */
  method: string;
  acceptance_criterion: string;
  sort_order: number;
  notes: string | null;
}

export interface Excipient {
  id: string;
  name: string;
  function: string | null;
  grade: string | null;
  compendial_status: string | null;
}

export interface Packaging {
  id: string;
  component: string;
  description: string;
  material: string | null;
}

export interface StabilityStudy {
  id: string;
  study_type: string;
  condition: string;
  duration_months: number;
  result_summary: string;
}
