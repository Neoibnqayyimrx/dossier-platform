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
