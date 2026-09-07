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
  /** Module 1 (P15a): null until someone says who is legally filing —
   * rule R14 blocks export while it is. */
  applicant: Applicant | null;
  declarations: Declaration[];
  /** P17: what KIND of application this is, which decides how much of
   * Modules 2-5 the dossier owes. */
  submission_type: string;
  /** Answers to the conditional sections, keyed by section number. Written
   * through PATCH /projects/{id}/conditions, never here. */
  condition_answers: Record<string, boolean>;
  created_at: string;
  updated_at: string;
}

/** Matches backend/app/schemas/applicant.py. Master data, owned like a
 * product: an agent filing a dozen products is one legal entity. */
export interface Applicant {
  id: string;
  company_name: string;
  address: string | null;
  country: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  authorized_representative_name: string | null;
  authorized_representative_title: string | null;
  created_at: string;
  updated_at: string;
}

/** Matches backend/app/schemas/certificate.py. Every field but the type
 * is optional because the ROW exists before the document does — "we need
 * a CPP, still pending" is a state the rules report on. */
export interface Certificate {
  id: string;
  product_id: string;
  certificate_type: string;
  issuing_authority: string | null;
  certificate_number: string | null;
  issue_date: string | null;
  expiry_date: string | null;
  manufacturer_id: string | null;
}

/** Matches backend/app/schemas/declaration.py. The signed/notarized flags
 * record something the platform cannot observe for itself — a human put
 * a pen on paper — which is why they are writable and why R15 blocks on
 * them. */
export interface Declaration {
  id: string;
  project_id: string;
  declaration_type: string;
  signed: boolean;
  signed_date: string | null;
  notarized: boolean;
  notarization_date: string | null;
}

/**
 * Matches backend/app/api/routers/regions.py.
 *
 * An EMPTY required list means "this region's Module 1 requirements are
 * not modelled yet", NOT "nothing is required" — say so in the UI rather
 * than implying a clean bill of health.
 */
export interface RegionProfile {
  region: Region;
  required_certificate_types: string[];
  required_declaration_types: string[];
  module1_slots: { slot_id: string; title: string }[];
}

/** Matches backend/app/schemas/validation.py::ValidationOverrideRead. */
export interface ValidationOverride {
  id: string;
  project_id: string;
  rule_id: string;
  reason: string;
  created_by_id: string;
  created_at: string;
  /** Null while the override stands. A withdrawn one keeps its original
   * reason — the row is the audit trail, so retracting adds a fact rather
   * than deleting one. */
  withdrawn_at: string | null;
  withdrawn_by_id: string | null;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
}

/** Matches backend/app/models/enums.py::UserRole -- lowercase, same
 * reasoning as NarrativeStatus below (Pydantic serializes `.value`). */
export type UserRole = "user" | "admin";

/** Matches backend/app/schemas/user.py::UserRead. */
export interface User {
  id: string;
  email: string;
  is_active: boolean;
  role: UserRole;
  created_at: string;
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

/** Matches backend/app/ctd/region_profiles.py::Applicability — what the
 * guideline says about a section, before the filer answers anything. */
export type Applicability = "required" | "conditional" | "not-applicable";

/** What the filer sees: not what the guideline requires, but where this
 * dossier actually stands on that leaf. Matches the four STATUS_*
 * constants in backend/app/api/routers/applicability.py. */
export type SectionStatusValue =
  | "produced"
  | "not-applicable"
  | "placeholder"
  | "outstanding";

/** Matches backend/app/api/routers/applicability.py::SectionStatusRead.
 *
 * Deliberately served rather than assembled here: the applicability table
 * is regulatory config, and a copy in TypeScript would drift into telling
 * a filer a section they owe is not applicable. */
/** Matches backend SectionCopyRead: one COPY of a repeated section (P19).
 *
 * A product with two actives owes two complete 3.2.S.1 documents. The
 * section list shows the copies rather than one row per number, because a
 * row per number understates the dossier by exactly the amount that makes
 * repetition worth having. */
export interface SectionCopy {
  key: string;
  subject: string;
}

export interface SectionStatus {
  number: string;
  module: number;
  title: string;
  applicability: Applicability;
  status: SectionStatusValue;
  /** Set iff applicability is "conditional": the question to answer. */
  condition: string | null;
  /** null = nobody has answered yet, which rule R19 reports as a WARNING. */
  answer: boolean | null;
  /** The guideline cited in the statement, when one is being filed. */
  citation: string | null;
  /** The axis this section repeats along ("drug_substance", "pack", …), or
   * null when it appears exactly once. */
  repeat: string | null;
  /** What this project actually owes along that axis. Empty for a section
   * that appears once. */
  copies: SectionCopy[];
}

/** Matches backend/app/api/routers/documents.py::SectionDocumentRead.
 *
 * The real third-party paper: a regulator's CPP, a CRO's study report. The
 * platform can place and checksum it; it can never author it. */
export interface SectionDocument {
  id: string;
  section_number: string;
  subject_slug: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  md5: string;
  uploaded_at: string;
  /** Server-built under `projects/{id}/` — never constructed here, so the
   * path convention stays one piece of server-side knowledge. */
  storage_key: string;
}

/** Matches backend/app/schemas/ctd.py::OverrideSummaryRead. */
export interface OverrideSummary {
  rule_id: string;
  reason: string;
}

export interface CtdBuildResponse {
  storage_key: string;
  files: { path: string; md5: string }[];
  /** Deterministic checks this build was allowed to ignore. A package
   * assembled over a waived error looks identical to a clean one, so the
   * build has to say so. */
  overrides: OverrideSummary[];
}

export interface EctdBuildResponse {
  storage_key: string;
  sequence_number: string;
  operations: Record<string, string>;
  overrides: OverrideSummary[];
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
  /** P20: which of the three things this row is a specification OF.
   * Derived on the backend from whichever foreign key is set, so it can
   * never disagree with the owner. */
  owner_kind?: SpecificationOwnerKind;
}

/** The three things the CTD asks for a specification of: 3.2.S.4.1 of the
 * drug substance, 3.2.P.4.1 of each excipient, 3.2.P.5.1 of the finished
 * product. One table, one editor -- three editors that drift is the
 * failure mode this replaced. */
export type SpecificationOwnerKind =
  | "drug-substance"
  | "drug-product"
  | "excipient";

/** The URL segment each owner's specification hangs under. Keyed by owner
 * kind so a caller names the OWNER, not a path. */
export const SPECIFICATION_PARENT: Record<SpecificationOwnerKind, string> = {
  "drug-substance": "apis",
  "drug-product": "products",
  excipient: "excipients",
};

/** Which section number an owner's specification renders into. Shown in
 * the editor's heading so the filer can see, while typing, which page of
 * the dossier they are filling in. */
export const SPECIFICATION_SECTION: Record<SpecificationOwnerKind, string> = {
  "drug-substance": "3.2.S.4.1",
  "drug-product": "3.2.P.5.1",
  excipient: "3.2.P.4.1",
};

/** One batch put forward in 3.2.S.4.4 / 3.2.P.5.4. */
export interface BatchAnalysis {
  id: string;
  batch_number: string;
  manufacture_date: string | null;
  batch_size: string | null;
  manufacturer_id: string | null;
  purpose: string | null;
  notes: string | null;
  owner_kind?: SpecificationOwnerKind;
  results: BatchAnalysisResult[];
}

/** One measured value, against one specification test, for one batch.
 * `specification_test_id` is a foreign key, not a test name typed again:
 * a result cannot be recorded for a test that is not in the
 * specification, because there would be no id to send. */
export interface BatchAnalysisResult {
  id: string;
  batch_analysis_id: string;
  specification_test_id: string;
  result: string;
  sort_order: number;
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

/** One stability study (3.2.S.7 / 3.2.P.8).
 *
 * P21 gave it the axes a real study has. Before, it was one row per
 * product with a free-text `result_summary`; now it is a study OF
 * something (`owner_kind`), run on a BATCH, stored in a PACK, with its
 * results as data. `result_summary` is gone -- what replaced it is
 * `results` below, plus a `notes` field that is never rendered as the
 * section's conclusion. */
export interface StabilityStudy {
  id: string;
  study_type: string;
  condition: string;
  duration_months: number;
  batch_analysis_id: string | null;
  packaging_id: string | null;
  protocol: string | null;
  notes: string | null;
  owner_kind?: StabilityOwnerKind;
  results: StabilityResult[];
  /** How far the study actually holds: the last timepoint before its first
   * out-of-specification result, or the last one on file if nothing
   * failed. Derived on the backend from the same function rule R05 checks
   * against -- `null` means no timepoint data has been entered. */
  longest_passing_timepoint: number | null;
}

/** One test, at one timepoint, in one study. `specification_test_id` is a
 * foreign key, not a test name typed again: a stability result cannot be
 * recorded for a test that is not in the specification, because there
 * would be no id to send. */
export interface StabilityResult {
  id: string;
  stability_study_id: string;
  specification_test_id: string;
  timepoint_months: number;
  result: string;
  sort_order: number;
  /** Derived on the backend, never stored. `null` is a third state and
   * never means "passed". */
  meets_criterion: boolean | null;
}

/** The two things the CTD asks for stability data of: 3.2.S.7 of each drug
 * substance, 3.2.P.8 of the finished product. No excipient leaf exists,
 * which is why this is narrower than SpecificationOwnerKind. */
export type StabilityOwnerKind = "drug-substance" | "drug-product";

/** Which section an owner's stability data renders into. Shown in the grid
 * so the filer can see which page they are filling in. */
export const STABILITY_SECTION: Record<StabilityOwnerKind, string> = {
  "drug-substance": "3.2.S.7.3",
  "drug-product": "3.2.P.8.3",
};
